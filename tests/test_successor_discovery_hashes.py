"""Corrections seal raw discovery bytes; source bundles seal normalized content."""
from pathlib import Path
import pytest
from scripts import work_memory
from tests.test_work_memory import corrected_successor_events

@pytest.fixture
def discovery_correction(tmp_path: Path):
    relative = 'operations/sequences/discovery/captured.md'
    document = tmp_path / relative
    document.parent.mkdir(parents=True)
    document.write_text(
        'CreatedAtUtc: 2026-09-07T00:00:00Z\nStatus: active\n'
        '## Intended Outcome\nResume selected work.\n'
        '## Why This Looks Repeatable\nRepeated recovery.\n'
        '## Required Inputs, Auth, Or Environment\nSaved checkpoint.\n'
        '## Commands And Observations\nUse the saved plan.\n'
        '## Failure Handling\nPreserve the completed work.\n'
        '## Verified Path\nTargeted resume.\n'
        '## Promotion Readiness\nAwait verification.\n'
    )
    raw_hash = work_memory.sha256_bytes(document.read_bytes())
    semantic_hash = work_memory.sha256_bytes(work_memory.semantic_discovery_bytes(document))
    assert raw_hash != semantic_hash
    rows = corrected_successor_events()[:6]
    correction = next(row for row in rows if row['event_type'] == 'correction_recorded')
    transition = next(row for row in rows if row['event_type'] == 'bundle_transition_recorded')
    for row in (correction, transition):
        row['changed_artifacts'] = [relative]
        row['changed_artifact_hashes'] = [raw_hash]
    bundle = [{'repository_key': 'memory-knowledge', 'path': relative, 'sha256': semantic_hash}]
    bundle_hash = work_memory.sha256_bytes(work_memory.canonical_bytes(bundle))
    transition['new_bundle_hash'] = bundle_hash
    kwargs = dict(lineage_id='lineage', source_bundle=bundle,
        source_bundle_hash=bundle_hash, predecessor_run_id=rows[0]['run_id'],
        correction_ids=[correction['correction_id']],
        repository_roots={'memory-knowledge': str(tmp_path)})
    return rows, kwargs, document, transition

@pytest.mark.parametrize('transition_matches', [True, False])
def test_sealed_discovery_bytes_survive_bundle_digest_domain(discovery_correction, transition_matches):
    rows, kwargs, _, transition = discovery_correction
    if not transition_matches:
        transition['new_bundle_hash'] = 'f' * 64
    work_memory._validate_successor_corrections(rows, **kwargs)

@pytest.mark.parametrize('transition_matches', [True, False])
def test_unsealed_discovery_bytes_are_refused(discovery_correction, transition_matches):
    rows, kwargs, document, transition = discovery_correction
    if not transition_matches:
        transition['new_bundle_hash'] = 'f' * 64
    document.write_text(document.read_text() + '\nUnrecorded command change.\n')
    with pytest.raises(work_memory.WorkMemoryError, match='successor-correction-(artifact-hash|bundle)-mismatch'):
        work_memory._validate_successor_corrections(rows, **kwargs)
