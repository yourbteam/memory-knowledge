from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from memory_knowledge.workflows import learned_memory


class Context:
    def __init__(self, value=None, enter=None, exit=None):
        self.value, self.enter, self.exit = value, enter, exit

    async def __aenter__(self):
        if self.enter: self.enter()
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        if self.exit: self.exit()
        return False


class ReviewPool:
    def __init__(self):
        self.in_transaction = False; self.executed = []
        self.entity_key = uuid.uuid4()

    async def fetchrow(self, query, *args):
        if "catalog.repositories" in query:
            return {"id": 7, "repository_key": "repo"}
        raise AssertionError(query)

    def acquire(self):
        return Context(self)

    def transaction(self):
        return Context(enter=lambda: setattr(self, "in_transaction", True),
                       exit=lambda: setattr(self, "in_transaction", False))

    async def fetchrow(self, query, *args):
        if "FOR UPDATE OF lr" in query:
            assert self.in_transaction
            return {
                "id": 11, "entity_id": 12, "scope_entity_id": 13,
                "memory_type": "operator_note", "title": "Root cause", "body_text": "A stable cause.",
                "confidence": 0.8, "applicability_mode": "repository",
                "source_kind": "operator_note", "verification_status": "unverified",
                "is_active": True, "content_kind": "root-cause",
                "evidence_refs": [{"kind": "revision"}], "evidence_resolution_errors": [],
                "entity_key": self.entity_key, "repository_id": 7, "repository_key": "repo",
            }
        if "catalog.repositories" in query:
            return {"id": 7, "repository_key": "repo"}
        assert self.in_transaction
        if "SELECT entity_key FROM catalog.entities" in query:
            return {"entity_key": uuid.uuid4()}
        if "SELECT e.entity_key" in query:
            return None
        raise AssertionError(query)

    async def execute(self, query, *args):
        assert self.in_transaction
        self.executed.append((query, args)); return "UPDATE 1"


@pytest.mark.asyncio
async def test_operator_note_approval_holds_row_lock_transaction():
    pool = ReviewPool()
    result = await learned_memory.run_commit(
        repository_key="repo", proposal_id=str(pool.entity_key), approval_status="approve",
        run_id=uuid.uuid4(), pool=pool,
    )
    assert result.status == "success" and result.data["status"] == "human_asserted"
    assert any("verification_status=$2" in query for query, _ in pool.executed)
    assert not pool.in_transaction


@pytest.mark.asyncio
async def test_candidate_listing_keeps_inactive_legacy_visible():
    class CandidatePool:
        async def fetchrow(self, query, *args):
            return {"id": 7, "repository_key": "repo"}

        async def fetch(self, query, *args):
            assert "lr.is_active=TRUE AND lr.verification_status='unverified'" in query
            assert "lr.content_kind IS NULL" in query
            return [{
                "id": 1, "entity_key": uuid.uuid4(), "title": "Legacy", "body_text": "Legacy body",
                "content_kind": None, "evidence_refs": None,
                "evidence_resolution_errors": [{"reason_code": "legacy"}], "confidence": 0.5,
                "created_utc": datetime.now(UTC), "is_active": False,
                "verification_status": "verified",
            }]

    result = await learned_memory.list_repo_note_candidates(CandidatePool(), "repo")
    assert len(result["items"]) == 1 and result["items"][0]["is_active"] is False
