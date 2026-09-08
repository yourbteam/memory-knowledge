"""Read-only Description handoff schema; does not certify or export runs."""

import argparse
import json
import re

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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Print the Description handoff schema; this command does not export runs.",
        allow_abbrev=False,
    )
    parser.add_argument("--schema", action="store_true", required=True,
                        help="print the schema without reading a run")
    parser.parse_args(argv)
    print(json.dumps(handoff_schema(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
