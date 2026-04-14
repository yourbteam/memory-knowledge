from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from memory_knowledge import server
from memory_knowledge.admin import actor_adaptation


class DummyPool:
    pass


@pytest.mark.asyncio
async def test_actor_adaptation_summary_returns_cautious_mode_for_low_quality_actor(monkeypatch):
    async def fake_quality(*args, **kwargs):
        return {
            "summary": [
                {
                    "run_count": 3,
                    "avg_score": 58.0,
                    "planning_context": {"projects": [{"project_key": "project-1", "project_name": "Project 1"}], "features": [], "tasks": []},
                }
            ]
        }

    async def fake_convergence(*args, **kwargs):
        return {
            "summary": [
                {
                    "run_count": 3,
                    "primary_recommendation": "ADD_PRE_RETRY_GROUNDING",
                    "planning_context": {"projects": [{"project_key": "project-1", "project_name": "Project 1"}], "features": [], "tasks": []},
                }
            ]
        }

    async def fake_entropy(*args, **kwargs):
        return {"targets": [{"score": 90, "planning_context": {"projects": [{"project_key": "project-1", "project_name": "Project 1"}], "features": [], "tasks": []}}]}

    monkeypatch.setattr(actor_adaptation.analytics, "get_quality_grade_summary", fake_quality)
    monkeypatch.setattr(actor_adaptation.analytics, "get_convergence_recommendation_summary", fake_convergence)
    monkeypatch.setattr(actor_adaptation.analytics, "list_entropy_sweep_targets", fake_entropy)

    data = await actor_adaptation.get_actor_adaptation_summary(
        DummyPool(),
        repository_key="repo-a",
        actor_email="user@example.com",
        workflow_name="wf-a",
    )

    assert data["match_found"] is True
    assert data["adaptation_mode"] == "cautious"
    assert data["confidence_delta"] == -0.1
    assert data["requires_stronger_clarification"] is True
    assert data["team_key"] == "project:project-1"


@pytest.mark.asyncio
async def test_actor_adaptation_summary_returns_empty_neutral_shape(monkeypatch):
    async def empty_summary(*args, **kwargs):
        return {"summary": []}

    async def empty_targets(*args, **kwargs):
        return {"targets": []}

    monkeypatch.setattr(actor_adaptation.analytics, "get_quality_grade_summary", empty_summary)
    monkeypatch.setattr(actor_adaptation.analytics, "get_convergence_recommendation_summary", empty_summary)
    monkeypatch.setattr(actor_adaptation.analytics, "list_entropy_sweep_targets", empty_targets)

    data = await actor_adaptation.get_actor_adaptation_summary(
        DummyPool(),
        repository_key="repo-a",
        actor_email="user@example.com",
    )

    assert data["match_found"] is False
    assert data["adaptation_mode"] == "balanced"
    assert data["confidence_delta"] == 0.0


@pytest.mark.asyncio
async def test_get_actor_adaptation_summary_tool_validates_and_returns_data(monkeypatch):
    monkeypatch.setattr(server, "get_pg_pool", lambda: DummyPool())
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())

    async def fake_summary(*args, **kwargs):
        return {"match_found": True, "adaptation_mode": "streamlined", "confidence_delta": 0.05}

    monkeypatch.setattr(server._actor_adaptation, "get_actor_adaptation_summary", fake_summary)

    result = await server.get_actor_adaptation_summary(repository_key="repo-a", actor_email="user@example.com")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["adaptation_mode"] == "streamlined"

    result = await server.get_actor_adaptation_summary(repository_key="", actor_email="user@example.com")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "repository_key is required"

    result = await server.get_actor_adaptation_summary(repository_key="repo-a", actor_email="")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["error"] == "actor_email is required"
