import json
from types import SimpleNamespace

import pytest

from memory_knowledge import server


@pytest.fixture
def intake_env(monkeypatch):
    pool = object()
    monkeypatch.setattr(server, "get_pg_pool", lambda: pool)
    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: None)
    return pool


@pytest.mark.asyncio
async def test_create_intake_session_tool(monkeypatch, intake_env):
    async def fake_create_session(pool, **kwargs):
        assert pool is intake_env
        assert kwargs["mode"] == "full"
        assert kwargs["title"] == "Butler development"
        assert kwargs["repository_key"] is None
        return {
            "session_key": "intake_abc123",
            "status": "active",
            "created_utc": "2026-04-22T10:00:00Z",
        }

    monkeypatch.setattr(server._intake, "create_session", fake_create_session)
    result = await server.create_intake_session(mode="full", title="Butler development")
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["session_key"] == "intake_abc123"


@pytest.mark.asyncio
async def test_append_intake_event_tool(monkeypatch, intake_env):
    async def fake_append_event(pool, **kwargs):
        assert kwargs["session_key"] == "intake_abc123"
        assert kwargs["role"] == "user"
        assert kwargs["event_type"] == "message"
        assert kwargs["idempotency_key"] == "turn-1"
        return {"event_key": "evt_001", "sequence": 1, "session_key": "intake_abc123"}

    monkeypatch.setattr(server._intake, "append_event", fake_append_event)
    result = await server.append_intake_event(
        session_key="intake_abc123",
        role="user",
        event_type="message",
        content_text="hello",
        idempotency_key="turn-1",
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["sequence"] == 1


@pytest.mark.asyncio
async def test_get_intake_session_state_tool_returns_compact_state(monkeypatch, intake_env):
    async def fake_get_state(pool, **kwargs):
        assert kwargs["include_recent_events"] is True
        assert kwargs["recent_event_limit"] == 5
        return {
            "session": {"session_key": "intake_abc123", "status": "active"},
            "distilled_context": {"revision": 1, "distilled_context": {"goal": "Build"}},
            "latest_draft": {"revision": 1},
            "recent_events": [{"sequence": 1}, {"sequence": 2}],
            "asset_refs": [],
            "workflow_links": [],
        }

    monkeypatch.setattr(server._intake, "get_session_state", fake_get_state)
    result = await server.get_intake_session_state(
        session_key="intake_abc123",
        include_recent_events=True,
        recent_event_limit=5,
    )
    payload = json.loads(result)
    assert payload["status"] == "success"
    assert payload["data"]["recent_events"][-1]["sequence"] == 2


@pytest.mark.asyncio
async def test_update_intake_distilled_context_surfaces_revision_conflict(monkeypatch, intake_env):
    async def fake_update_context(pool, **kwargs):
        assert kwargs["expected_revision"] == 11
        return {
            "ok": False,
            "errorCode": "REVISION_CONFLICT",
            "error": "Expected revision 11 but current revision is 12",
            "current_revision": 12,
        }

    monkeypatch.setattr(server._intake, "update_distilled_context", fake_update_context)
    result = await server.update_intake_distilled_context(
        session_key="intake_abc123",
        expected_revision=11,
        updated_from_sequence=26,
        distilled_context={"goal": "Build"},
    )
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["data"]["errorCode"] == "REVISION_CONFLICT"
    assert payload["data"]["current_revision"] == 12


@pytest.mark.asyncio
async def test_save_finalize_and_link_intake_tools(monkeypatch, intake_env):
    async def fake_save(pool, **kwargs):
        assert kwargs["status"] == "draft"
        return {
            "draft_revision_key": "draft_rev_001",
            "revision": 1,
            "session_key": "intake_abc123",
        }

    async def fake_finalize(pool, **kwargs):
        assert kwargs["final_draft_revision"] == 1
        return {
            "session_key": "intake_abc123",
            "status": "finalized",
            "finalized_utc": "2026-04-22T10:15:00Z",
        }

    async def fake_link(pool, **kwargs):
        assert kwargs["workflow_name"] == "requirements-hardening-workflow"
        return {"link_key": "link_001"}

    monkeypatch.setattr(server._intake, "save_draft_revision", fake_save)
    monkeypatch.setattr(server._intake, "finalize_session", fake_finalize)
    monkeypatch.setattr(server._intake, "link_workflow_run", fake_link)

    saved = json.loads(
        await server.save_intake_draft_revision(
            session_key="intake_abc123",
            draft_json={"title": "Butler development"},
        )
    )
    finalized = json.loads(
        await server.finalize_intake_session(
            session_key="intake_abc123",
            final_draft_revision=1,
            project_key="workflow-orch",
        )
    )
    linked = json.loads(
        await server.link_intake_workflow_run(
            session_key="intake_abc123",
            run_id="9ebd5c7e-8d71-4bf9-9af6-e6f95607f629",
            workflow_name="requirements-hardening-workflow",
            link_type="requirements_hardening",
        )
    )

    assert saved["data"]["revision"] == 1
    assert finalized["data"]["status"] == "finalized"
    assert linked["data"]["link_key"] == "link_001"


@pytest.mark.asyncio
async def test_list_intake_events_asset_refs_and_sessions(monkeypatch, intake_env):
    async def fake_list_events(pool, **kwargs):
        assert kwargs["from_sequence"] == 1
        return {"events": [{"event_key": "evt_001", "sequence": 1}]}

    async def fake_add_asset(pool, **kwargs):
        assert kwargs["event_key"] == "evt_001"
        return {"asset_ref_key": "asset_001"}

    async def fake_list_sessions(pool, **kwargs):
        assert kwargs["actor_email"] == "user@example.com"
        return {
            "sessions": [
                {
                    "session_key": "intake_abc123",
                    "status": "active",
                    "mode": "full",
                    "title": "Butler development",
                }
            ]
        }

    monkeypatch.setattr(server._intake, "list_events", fake_list_events)
    monkeypatch.setattr(server._intake, "add_asset_ref", fake_add_asset)
    monkeypatch.setattr(server._intake, "list_sessions_by_actor", fake_list_sessions)

    events = json.loads(await server.list_intake_events(session_key="intake_abc123"))
    asset = json.loads(
        await server.add_intake_asset_ref(
            session_key="intake_abc123",
            event_key="evt_001",
            asset_type="screenshot",
            display_name="Screenshot.png",
            uri="opaque-ref",
        )
    )
    sessions = json.loads(
        await server.list_intake_sessions_by_actor(actor_email="user@example.com")
    )

    assert events["data"]["events"][0]["event_key"] == "evt_001"
    assert asset["data"]["asset_ref_key"] == "asset_001"
    assert sessions["data"]["sessions"][0]["session_key"] == "intake_abc123"


@pytest.mark.asyncio
async def test_intake_write_tool_respects_remote_write_guard(monkeypatch):
    class Guard:
        run_id = None

        def model_dump_json(self):
            return json.dumps({"status": "error", "run_id": self.run_id, "error": "guarded"})

    monkeypatch.setattr(server, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(server, "check_remote_write_guard", lambda settings, tool_name: Guard())
    result = await server.create_intake_session(title="Blocked")
    payload = json.loads(result)
    assert payload["status"] == "error"
    assert payload["run_id"]
