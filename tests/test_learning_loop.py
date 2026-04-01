"""Tests for agent retrieval learning loop components."""
import uuid
from unittest.mock import AsyncMock

import pytest

from memory_knowledge.admin.working_memory import VALID_OBSERVATION_TYPES
from memory_knowledge.projections.working_memory_neo4j import _OBSERVATION_TYPE_TO_REL
from memory_knowledge.workflows.learned_memory import VALID_MEMORY_TYPES


# ── query_rewrite observation type ──


def test_query_rewrite_in_valid_observation_types():
    assert "query_rewrite" in VALID_OBSERVATION_TYPES


def test_query_rewrite_neo4j_rel_mapping():
    assert _OBSERVATION_TYPE_TO_REL["query_rewrite"] == "REWROTE_QUERY_FOR"


def test_all_observation_types_have_neo4j_mapping():
    missing = VALID_OBSERVATION_TYPES - set(_OBSERVATION_TYPE_TO_REL.keys())
    assert not missing, f"Missing Neo4j mappings: {missing}"


# ── memory_type vocabulary ──


def test_valid_memory_types_defined():
    assert len(VALID_MEMORY_TYPES) >= 5
    assert "prompt_pattern" in VALID_MEMORY_TYPES
    assert "retrieval_strategy" in VALID_MEMORY_TYPES
    assert "common_issue" in VALID_MEMORY_TYPES


def test_memory_type_all_fit_varchar50():
    for mt in VALID_MEMORY_TYPES:
        assert len(mt) <= 50, f"memory_type '{mt}' exceeds VARCHAR(50)"


@pytest.mark.asyncio
async def test_memory_type_validation_rejects_invalid():
    from memory_knowledge.workflows.learned_memory import run_proposal

    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value={"id": 1})

    result = await run_proposal(
        repository_key="test-repo",
        memory_type="invalid_type_not_in_vocabulary",
        title="test title",
        body_text="test body",
        evidence_entity_key=str(uuid.uuid4()),
        scope_entity_key=str(uuid.uuid4()),
        confidence=0.5,
        applicability_mode="repository",
        run_id=uuid.uuid4(),
        pool=mock_pool,
    )
    assert result.status == "error"
    assert "Invalid memory_type" in result.error
