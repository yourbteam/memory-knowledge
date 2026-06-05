"""T3 fail-loud: a run that dropped files reports 'partial', not clean success."""

from memory_knowledge.workflows.ingestion import _ingestion_outcome


def test_outcome_clean_run_is_success():
    assert _ingestion_outcome(0) == ("completed", "success")


def test_outcome_any_failure_is_partial():
    assert _ingestion_outcome(1) == ("partial", "partial")
    assert _ingestion_outcome(50) == ("partial", "partial")
