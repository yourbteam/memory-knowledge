from __future__ import annotations

import json

from scripts import sequence_intake_adapters, sequence_intake_doc_projection


def test_projection_is_idempotent():
    document = "# Example\n\nBody.\n"

    projected = sequence_intake_doc_projection.project(document)

    assert sequence_intake_doc_projection.project(projected) == projected
    assert projected.count(sequence_intake_doc_projection.BEGIN) == 1
    assert projected.count(sequence_intake_doc_projection.END) == 1


def test_every_registered_sequence_projects_shared_intake_runtime():
    assert sequence_intake_doc_projection.run(check=True) == 0

    for sequence_id in sequence_intake_adapters.CANONICAL_SEQUENCE_IDS:
        folder = (
            sequence_intake_doc_projection.ROOT
            / "operations"
            / "sequences"
            / sequence_id
        )
        document = (folder / "sequence.md").read_text(encoding="utf-8")
        manifest = json.loads(
            (folder / "dependencies.json").read_text(encoding="utf-8")
        )
        dependencies = {
            (
                item["kind"],
                item["repository_key"],
                item["path_or_sequence_id"],
            )
            for item in manifest["dependencies"]
        }

        assert document.count(sequence_intake_doc_projection.BEGIN) == 1
        assert document.count(sequence_intake_doc_projection.END) == 1
        for path in sequence_intake_doc_projection.SHARED_DEPENDENCIES:
            assert ("file", "memory-knowledge", path) in dependencies
