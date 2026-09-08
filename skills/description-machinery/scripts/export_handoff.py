"""Publish the handoff schema or opt in to verifying and sealing a Description run."""

import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys

MAX_SOURCE_BYTES = 32 * 1024 * 1024

HANDOFF_FIELDS = (
    "schema_version", "machinery", "contract_version", "run_identity",
    "input_state_sha256", "questions_sha256", "context_sha256", "reader_records",
    "description", "source_objects", "terminal_state", "exporter_source_sha256",
    "handoff_sha256",
)
READER_RECORD_FIELDS = ("question_id", "seat", "path", "sha256", "answer_sha256")
DESCRIPTION_FIELDS = ("path", "sha256")
SOURCE_OBJECT_FIELDS = ("origin", "sha256")
QUESTION_IDS = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8")
READER_SEATS = ("look-1", "look-2")
MACHINERY_VALUES = ("description-machinery",)
TERMINAL_STATES = ("complete",)
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def handoff_schema():
    """Return a fresh schema, never a claim that a run is complete."""
    digest = {"$ref": "#/$defs/sha256"}
    path = {"type": "string", "minLength": 1}

    def closed(fields, properties):
        if set(fields) != set(properties):
            raise ValueError("schema properties differ from the named field declaration")
        return {"type": "object", "properties": properties,
                "required": list(fields), "additionalProperties": False}

    reader = closed(READER_RECORD_FIELDS, {
        "question_id": {"enum": list(QUESTION_IDS)}, "seat": {"enum": list(READER_SEATS)},
        "path": dict(path), "sha256": dict(digest), "answer_sha256": dict(digest),
    })
    result = closed(HANDOFF_FIELDS, {
        "schema_version": {"type": "integer", "const": 1},
        "machinery": {"enum": list(MACHINERY_VALUES)},
        "contract_version": {"type": "integer", "const": 1},
        "run_identity": dict(path),
        "input_state_sha256": dict(digest), "questions_sha256": dict(digest),
        "context_sha256": dict(digest),
        "reader_records": {"type": "array", "items": reader, "minItems": 16,
                           "maxItems": 16, "uniqueItems": True},
        "description": closed(DESCRIPTION_FIELDS, {"path": dict(path), "sha256": dict(digest)}),
        "source_objects": {"type": "array", "minItems": 1, "uniqueItems": True,
                           "items": closed(SOURCE_OBJECT_FIELDS, {
                               "origin": dict(path), "sha256": dict(digest)})},
        "terminal_state": {"enum": list(TERMINAL_STATES)},
        "exporter_source_sha256": dict(digest), "handoff_sha256": dict(digest),
    })
    result["properties"]["reader_records"]["allOf"] = [
        {"contains": {"properties": {"question_id": {"const": question},
                                     "seat": {"const": seat}}},
         "minContains": 1, "maxContains": 1}
        for question in QUESTION_IDS for seat in READER_SEATS
    ]
    result["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    result["title"] = "Description handoff v1"
    result["description"] = (
        "Shape only. Export must verify source bytes, exact reader agreement and final assembly. "
        "handoff_sha256 hashes canonical JSON omitting that top-level field; "
        "the complete file has a separate digest."
    )
    result["$defs"] = {"sha256": {"type": "string", "pattern": SHA256.pattern, "maxLength": 64}}
    return result


class ExportError(ValueError):
    """A specific input or publication boundary could not be verified."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def absolute(value):
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != str(value):
        raise ExportError(f"path {value!r} must be a normalized absolute path without '..'")
    return path


@contextmanager
def directory_fd(path):
    """Walk every component without following symbolic links, keeping the last fd pinned."""
    path = absolute(str(path))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_regular(path):
    path = absolute(str(path))
    with directory_fd(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise ExportError(f"{path}: require a regular file with no hard-link alias")
            if before.st_size > MAX_SOURCE_BYTES:
                raise ExportError(f"{path}: exceeds the {MAX_SOURCE_BYTES}-byte input limit")
            chunks = []
            size = 0
            while True:
                chunk = os.read(fd, min(65536, MAX_SOURCE_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_SOURCE_BYTES:
                    raise ExportError(f"{path}: input grew beyond the byte limit")
            after = os.fstat(fd)
            stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
            if stamp(before) != stamp(after):
                raise ExportError(f"{path}: file changed during its read; supply stable evidence")
            return b"".join(chunks)
        finally:
            os.close(fd)


def json_value(data, label):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ExportError(f"{label}: duplicate JSON key {key!r}; supply one value")
            result[key] = value
        return result
    def invalid(value):
        raise ExportError(f"{label}: non-finite JSON value {value!r} is not permitted")
    try:
        return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExportError(f"{label}: invalid UTF-8 JSON: {error}") from None


def exact(value, fields, label):
    if type(value) is not dict:
        raise ExportError(f"{label}: require an object with fields {list(fields)!r}")
    missing, extra = sorted(set(fields) - value.keys()), sorted(value.keys() - set(fields))
    if missing or extra:
        raise ExportError(f"{label}: missing fields {missing!r}, unexpected fields {extra!r}")
    return value


class Evidence:
    def __init__(self):
        self.files = {}
        self.directories = {}

    def read(self, path):
        path = absolute(str(path))
        if path not in self.files:
            self.files[path] = read_regular(path)
        return self.files[path]

    def json(self, path):
        return json_value(self.read(path), str(path))

    def names(self, path):
        path = absolute(str(path))
        with directory_fd(path) as fd:
            result = tuple(sorted(os.listdir(fd)))
        self.directories[path] = result
        return result

    def verify_unchanged(self):
        for path, before in self.files.items():
            if read_regular(path) != before:
                raise ExportError(f"{path}: evidence changed before sealing; no handoff was published")
        for path, before in self.directories.items():
            with directory_fd(path) as fd:
                after = tuple(sorted(os.listdir(fd)))
            if after != before:
                raise ExportError(f"{path}: member set changed before sealing")


def source_binding(value, label):
    exact(value, ("path", "sha256"), label)
    absolute(value["path"])
    if type(value["sha256"]) is not str or not SHA256.fullmatch(value["sha256"]):
        raise ExportError(f"{label}.sha256: require exactly 64 lowercase hex characters")
    return value


def validate_run(run, source_manifest=None):
    """Reconstruct completion from frozen evidence without invoking the stateful drive."""
    run = absolute(str(run))
    evidence = Evidence()
    state = exact(evidence.json(run / "input-state.json"),
                  ("contract", "intent", "context", "owner_answers", "questions_sha256"), "input-state")
    if type(state["contract"]) is not int or state["contract"] != 1:
        raise ExportError("input-state.contract: require integer 1")
    if type(state["context"]) is not list:
        raise ExportError("input-state.context: require an ordered source list")
    sources = [source_binding(state["intent"], "intent")]
    sources += [source_binding(row, f"context[{i}]") for i, row in enumerate(state["context"])]
    if state["owner_answers"] is not None:
        sources.append(source_binding(state["owner_answers"], "owner_answers"))
    origins = [row["path"] for row in sources]
    if len(set(origins)) != len(origins):
        raise ExportError("input-state: repeated source identity; require unique source paths")

    # Read only the literal question contract; never execute the upstream drive.
    producer = Path(__file__).absolute().parents[1] / "from_intent.py"
    tree = ast.parse(evidence.read(producer).decode("utf-8"), filename=str(producer))
    questions = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "QUESTIONS":
            questions = ast.literal_eval(node.value)
    if questions is None or [row["id"] for row in questions] != list(QUESTION_IDS):
        raise ExportError("Description question contract is unavailable or incompatible")
    if state["questions_sha256"] != digest(canonical(questions)):
        raise ExportError("input-state.questions_sha256: fixed questions changed")
    saved_questions = exact(evidence.json(run / "questions.json"), ("questions",), "questions.json")
    if saved_questions["questions"] != questions:
        raise ExportError("questions.json: stored questions differ from the fixed contract")
    context = exact(evidence.json(run / "context.json"), ("context", "owner_answers"), "context.json")
    expected_context = {"context": [row["path"] for row in state["context"]],
                        "owner_answers": state["owner_answers"]["path"] if state["owner_answers"] else None}
    if context != expected_context:
        raise ExportError("context.json: identities or ordering differ from input-state")

    locations = {row["path"]: row["path"] for row in sources}
    if source_manifest is not None:
        manifest = exact(evidence.json(absolute(str(source_manifest))), ("schema_version", "sources"), "source manifest")
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
            raise ExportError("source manifest.schema_version: require integer 1")
        if type(manifest["sources"]) is not list:
            raise ExportError("source manifest.sources: require one entry per input source")
        indexed = {}
        expected_hashes = {row["path"]: row["sha256"] for row in sources}
        for i, row in enumerate(manifest["sources"]):
            exact(row, ("origin", "path", "sha256"), f"source manifest.sources[{i}]")
            origin = str(absolute(row["origin"]))
            if origin in indexed or origin not in expected_hashes or row["sha256"] != expected_hashes[origin]:
                raise ExportError(f"source manifest.sources[{i}]: duplicate, unknown or hash-substituted origin {origin!r}")
            indexed[origin] = str(absolute(row["path"]))
        if set(indexed) != set(origins):
            raise ExportError("source manifest: require exactly the complete input-state source set")
        locations = indexed
    source_text = {}
    source_objects = []
    for row in sources:
        location = locations[row["path"]]
        data = evidence.read(location)
        if digest(data) != row["sha256"]:
            raise ExportError(f"source {row['path']}: bytes differ from input-state; supply the exact captured bytes")
        try:
            source_text[row["path"]] = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ExportError(f"source {row['path']}: expected UTF-8 text") from None
        # 'origin' is the downstream import location. Logical citation identity stays in
        # the immutable input-state and reader records, verified against the same digest.
        item = {"origin": location, "sha256": row["sha256"]}
        if item not in source_objects:
            source_objects.append(item)

    records = {}
    reader_records = []
    expected_names = {qid + ".json" for qid in QUESTION_IDS}
    for seat in READER_SEATS:
        names = set(evidence.names(run / seat))
        if names - {"reader.json"} != expected_names:
            raise ExportError(f"{seat}: missing {sorted(expected_names - names)!r}, unexpected {sorted(names - expected_names - {'reader.json'})!r}")
        for qid in QUESTION_IDS:
            path = run / seat / (qid + ".json")
            row = exact(evidence.json(path), ("id", "answered", "answer", "quoted_from", "quote"), str(path))
            if row["id"] != qid or row["answered"] != "yes":
                raise ExportError(f"{seat}/{qid}: require matching identity and answered='yes'")
            quote, origin = row["quote"], row["quoted_from"]
            if type(quote) is not str or not quote.strip() or type(origin) is not str or origin not in source_text:
                raise ExportError(f"{seat}/{qid}: require a nonempty quote from a bound source")
            if type(row["answer"]) is not str or quote not in source_text[origin]:
                raise ExportError(f"{seat}/{qid}: require a string answer and a verbatim source quote")
            records[(seat, qid)] = row
            reader_records.append({"question_id": qid, "seat": seat, "path": str(path),
                                   "sha256": digest(evidence.read(path)), "answer_sha256": digest(canonical(row))})
    lines = ["# Description", "", f"About: {state['intent']['path']}", ""]
    for question in questions:
        left = records[(READER_SEATS[0], question["id"])]
        right = records[(READER_SEATS[1], question["id"])]
        if (left["quote"], left["quoted_from"]) != (right["quote"], right["quoted_from"]):
            raise ExportError(f"{question['id']}: reader source quotations disagree")
        lines.extend([f"## {question['id']} — {question['asks']}", "", left["quote"], "",
                      f"_Source: `{left['quoted_from']}`_", ""])
    description_path = run / "description.md"
    description_bytes = evidence.read(description_path)
    if description_bytes != "\n".join(lines).encode("utf-8"):
        raise ExportError("description.md: bytes differ from the complete agreed-reader assembly")
    expected_sheet = ("# What only you can answer\n\n"
                      f"About: {state['intent']['path']}\n\n"
                      "Everything was answered by what you gave. Nothing to ask.\n")
    if evidence.read(run / "to-ask.md") != expected_sheet.encode("utf-8"):
        raise ExportError("to-ask.md: run still has unresolved owner questions or changed completion evidence")
    handoff = {"schema_version": 1, "machinery": "description-machinery", "contract_version": 1,
               "run_identity": str(run), "input_state_sha256": digest(evidence.read(run / "input-state.json")),
               "questions_sha256": digest(evidence.read(run / "questions.json")),
               "context_sha256": digest(evidence.read(run / "context.json")), "reader_records": reader_records,
               "description": {"path": str(description_path), "sha256": digest(description_bytes)},
               "source_objects": source_objects, "terminal_state": "complete",
               "exporter_source_sha256": digest(evidence.read(Path(__file__).absolute()))}
    handoff["handoff_sha256"] = digest(canonical(handoff))
    return handoff, evidence


def validate_handoff(handoff):
    """Check the assembled wire contract and its non-self-referential digest."""
    exact(handoff, HANDOFF_FIELDS, "handoff")
    if type(handoff["schema_version"]) is not int or handoff["schema_version"] != 1:
        raise ExportError("handoff.schema_version: require integer 1")
    if type(handoff["contract_version"]) is not int or handoff["contract_version"] != 1:
        raise ExportError("handoff.contract_version: require integer 1")
    if handoff["machinery"] not in MACHINERY_VALUES or handoff["terminal_state"] not in TERMINAL_STATES:
        raise ExportError("handoff: unsupported machinery or terminal state")
    absolute(handoff["run_identity"])
    hashes = [handoff["input_state_sha256"], handoff["questions_sha256"], handoff["context_sha256"],
              handoff["exporter_source_sha256"], handoff["handoff_sha256"]]
    exact(handoff["description"], DESCRIPTION_FIELDS, "handoff.description")
    absolute(handoff["description"]["path"])
    hashes.append(handoff["description"]["sha256"])
    if type(handoff["reader_records"]) is not list or len(handoff["reader_records"]) != 16:
        raise ExportError("handoff.reader_records: require sixteen records")
    identities = []
    for row in handoff["reader_records"]:
        exact(row, READER_RECORD_FIELDS, "handoff reader")
        identities.append((row["question_id"], row["seat"]))
        absolute(row["path"])
        hashes.extend([row["sha256"], row["answer_sha256"]])
    if set(identities) != {(qid, seat) for qid in QUESTION_IDS for seat in READER_SEATS}:
        raise ExportError("handoff.reader_records: require exactly every question and seat")
    if type(handoff["source_objects"]) is not list or not handoff["source_objects"]:
        raise ExportError("handoff.source_objects: require verified source objects")
    for row in handoff["source_objects"]:
        exact(row, SOURCE_OBJECT_FIELDS, "handoff source")
        absolute(row["origin"])
        hashes.append(row["sha256"])
    if len({canonical(row) for row in handoff["source_objects"]}) != len(handoff["source_objects"]):
        raise ExportError("handoff.source_objects: duplicate source objects are forbidden")
    if any(type(value) is not str or SHA256.fullmatch(value) is None for value in hashes):
        raise ExportError("handoff: every hash must have exactly 64 lowercase hex characters")
    expected = digest(canonical({key: value for key, value in handoff.items() if key != "handoff_sha256"}))
    if handoff["handoff_sha256"] != expected:
        raise ExportError("handoff.handoff_sha256: sealed object digest differs")


def overlaps(left, right):
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def publish(run, output_root, output, target_repositories, product_boundaries, source_manifest=None):
    run, root, output = (absolute(str(value)) for value in (run, output_root, output))
    if not target_repositories or not product_boundaries:
        raise ExportError("publication requires explicit target repositories and product boundaries")
    excluded = [run, *map(lambda p: absolute(str(p)), target_repositories),
                *map(lambda p: absolute(str(p)), product_boundaries)]
    for boundary in excluded:
        try:
            resolved = boundary.resolve(strict=False)
        except (OSError, RuntimeError) as error:
            raise ExportError(f"excluded boundary {boundary}: cannot establish its identity: {error}") from None
        if resolved != boundary:
            raise ExportError(f"excluded boundary {boundary}: linked aliases are forbidden; supply its physical path")
    if not output.is_relative_to(root) or output == root:
        raise ExportError("output must be a file strictly below the authorized output root")
    if any(overlaps(root, boundary) for boundary in excluded):
        raise ExportError("output root overlaps a source run, target repository or product boundary")
    for parent in (root, *root.parents):
        if (parent / ".git").exists():
            raise ExportError("output root is inside a Git repository; choose external runtime storage")
    with directory_fd(root):
        pass
    with directory_fd(output.parent) as parent:
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ExportError(f"{output}: already exists; choose a new output file")
        handoff, evidence = validate_run(run, source_manifest)
        validate_handoff(handoff)
        if any(path == output or path.is_relative_to(root) for path in evidence.files):
            raise ExportError("output root contains an input artifact; choose disjoint runtime storage")
        payload = json.dumps(handoff, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
        evidence.verify_unchanged()
        stage = ".description-handoff-" + secrets.token_hex(16)
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        linked = False
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fchmod(stream.fileno(), 0o444)
                os.fsync(stream.fileno())
            evidence.verify_unchanged()
            with directory_fd(output.parent) as fresh:
                if (os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) != (os.fstat(parent).st_dev, os.fstat(parent).st_ino):
                    raise ExportError("output parent changed before publication")
            os.link(stage, output.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            linked = True
            os.fsync(parent)
        except BaseException:
            if linked:
                current = os.stat(output.name, dir_fd=parent, follow_symlinks=False)
                staged = os.stat(stage, dir_fd=parent, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (staged.st_dev, staged.st_ino):
                    os.unlink(output.name, dir_fd=parent)
            raise
        finally:
            os.unlink(stage, dir_fd=parent)
    return {"status": "exported", "path": str(output), "sha256": digest(payload),
            "handoff_sha256": handoff["handoff_sha256"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Print the schema or seal one completed Description run.",
                                     allow_abbrev=False)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--schema", action="store_true")
    operation.add_argument("--run", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--target-repository", action="append", type=Path)
    parser.add_argument("--product-boundary", action="append", type=Path)
    parser.add_argument("--source-snapshots", type=Path)
    args = parser.parse_args(argv)
    if args.schema:
        if any((args.output_root, args.output, args.target_repository, args.product_boundary, args.source_snapshots)):
            parser.error("--schema cannot be combined with export arguments")
        print(json.dumps(handoff_schema(), indent=2, sort_keys=True))
        return 0
    if not all((args.output_root, args.output, args.target_repository, args.product_boundary)):
        parser.error("--run requires --output-root, --output, --target-repository and --product-boundary")
    try:
        result = publish(args.run, args.output_root, args.output, args.target_repository,
                         args.product_boundary, args.source_snapshots)
    except (ExportError, OSError, ValueError, TypeError, SyntaxError) as error:
        print(json.dumps({"status": "refused", "reason": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
