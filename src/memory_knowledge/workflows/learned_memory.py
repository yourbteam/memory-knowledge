from __future__ import annotations

import hashlib
import base64
import json
import re
import time
import uuid
import urllib.parse
from decimal import Decimal
from collections.abc import Mapping
from typing import Any

import asyncpg
import neo4j
import structlog
from qdrant_client import AsyncQdrantClient

from memory_knowledge.config import Settings
from memory_knowledge.identity.entity_key import learned_record_entity_key
from memory_knowledge.projections.learned_memory_neo4j import project_learned_rule
from memory_knowledge.projections.learned_memory_qdrant import (
    deactivate_learned_record_point,
    embed_and_upsert_learned_record,
)
from memory_knowledge.projections.learned_memory_writer import (
    supersede_learned_record,
    update_verification_status,
    upsert_learned_record,
)
from memory_knowledge.workflows.base import WorkflowResult

logger = structlog.get_logger()

VALID_MEMORY_TYPES = {
    "prompt_pattern",
    "retrieval_strategy",
    "common_issue",
    "entity_relationship",
    "naming_convention",
    "architectural_pattern",
    "note",  # human-asserted, evidence-free repo-level note (author_repo_note)
    "operator_note",
}

ALLOWED_CONTENT_KINDS = {
    "root-cause",
    "corrected-approach",
    "repository-decision",
    "repository-fact",
}
ELIGIBLE_VERIFICATION_STATUSES = {"human_asserted", "verified"}
PROHIBITED_MEMORY_KEYS = {
    "person", "people", "contact", "relationship", "profile", "diary", "journal",
    "transcript", "conversation_history", "chat_history", "message_history",
}
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"(?:\?|&)sig=[^&\s]+", re.I),
)
_PERSONAL_PATTERNS = (
    re.compile(r"\b(my|our) (wife|husband|partner|mother|father|family|health)\b", re.I),
    re.compile(r"\b(i|we) (prefer|like|love|hate|feel|went|visited|ate|slept)\b", re.I),
    re.compile(r"\b(diary|journal) entry\b", re.I),
    re.compile(r"\b(user|personal) profile\b", re.I),
    re.compile(r"\b[A-Z][a-z]+\s+(prefers|likes|loves|hates|feels|visited|ate|slept)\b"),
)


def _operator_note(row: Mapping[str, Any]) -> bool:
    return row.get("source_kind") == "operator_note" or row.get("memory_type") in {"note", "operator_note"}


def learned_record_is_eligible(row: Mapping[str, Any]) -> bool:
    """Return the one automatic-influence decision used by every consumer."""
    if not bool(row.get("is_active")):
        return False
    status = row.get("verification_status")
    if _operator_note(row):
        refs = row.get("evidence_refs")
        return (
            status in ELIGIBLE_VERIFICATION_STATUSES
            and row.get("content_kind") in ALLOWED_CONTENT_KINDS
            and isinstance(refs, list)
            and bool(refs)
            and not row.get("evidence_resolution_errors")
        )
    return status == "verified"


IMPORT_OWNED_FIELDS = (
    "_entity_key", "_scope_entity_key", "memory_type", "title", "body_text",
    "source_kind", "confidence", "applicability_mode", "_valid_from_commit_sha",
    "_valid_to_commit_sha", "_evidence_entity_key", "_evidence_chunk_entity_key",
    "_supersedes_entity_key", "verification_status", "verification_notes", "is_active",
    "created_utc", "content_kind", "evidence_refs", "evidence_resolution_errors",
)


def normalize_import_owned_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the complete stable learned-record contract for collision checks."""
    result: dict[str, Any] = {}
    for field in IMPORT_OWNED_FIELDS:
        value = row.get(field)
        if field in {"_entity_key", "_scope_entity_key", "_evidence_entity_key",
                     "_evidence_chunk_entity_key", "_supersedes_entity_key"}:
            value = str(value).lower() if value is not None else None
        elif field == "confidence":
            value = format(Decimal(str(value if value is not None else "0.5")).normalize(), "f")
        elif field == "applicability_mode":
            value = value or "repository"
        elif field == "is_active":
            value = bool(value)
        elif field == "created_utc" and value is not None:
            value = value.isoformat() if hasattr(value, "isoformat") else str(value)
        elif field in {"evidence_refs", "evidence_resolution_errors"}:
            value = value if value is not None else None
            if value is not None:
                value = json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))
        result[field] = value
    return result


def validate_operational_content(
    *,
    title: str,
    body_text: str,
    content_kind: str,
    evidence_refs: list[dict[str, Any]],
) -> None:
    if content_kind not in ALLOWED_CONTENT_KINDS:
        raise ValueError("invalid-content-kind")
    if not title or not body_text or len(title) > 500 or len(body_text) > 4000:
        raise ValueError("invalid-operational-content")
    if not evidence_refs or len(evidence_refs) > 50:
        raise ValueError("missing-operational-evidence")
    text = f"{title}\n{body_text}"
    for _ in range(3):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        raise ValueError("prohibited-secret-shape")
    if any(pattern.search(text) for pattern in _PERSONAL_PATTERNS):
        raise ValueError("prohibited-memory-shape")
    for ref in evidence_refs:
        if any(str(key).lower().replace("-", "_") in PROHIBITED_MEMORY_KEYS for key in ref):
            raise ValueError("prohibited-memory-shape")


async def resolve_evidence_refs(
    pool: asyncpg.Pool,
    repository_key: str,
    evidence_refs: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Resolve input refs into a stable, repository-owned canonical representation."""
    repo = await pool.fetchrow(
        """
        SELECT id, repository_key FROM catalog.repositories
        WHERE lower(repository_key)=lower($1)
        ORDER BY (repository_key=$1) DESC, id ASC LIMIT 1
        """,
        repository_key,
    )
    if repo is None:
        raise ValueError("repository-not-found")
    canonical_key = repo["repository_key"]
    canonical: list[dict[str, Any]] = []
    for index, raw in enumerate(evidence_refs):
        if not isinstance(raw, dict) or raw.get("kind") not in {"entity", "file", "revision"}:
            raise ValueError(f"invalid-evidence-ref:{index}")
        raw_repo = str(raw.get("repository_key") or repository_key)
        if raw_repo.lower() != canonical_key.lower():
            raise ValueError(f"cross-repository-evidence:{index}")
        kind = raw["kind"]
        if kind == "entity":
            try:
                entity_key = str(uuid.UUID(str(raw["entity_key"])))
            except (KeyError, ValueError):
                raise ValueError(f"invalid-evidence-ref:{index}") from None
            found = await pool.fetchrow(
                "SELECT 1 FROM catalog.entities WHERE repository_id=$1 AND entity_key=$2",
                repo["id"], uuid.UUID(entity_key),
            )
            if found is None:
                raise ValueError(f"unresolved-evidence:{index}")
            item = {"kind": "entity", "repository_key": canonical_key, "entity_key": entity_key}
        else:
            commit = str(raw.get("revision_commit") or "").lower()
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError(f"invalid-evidence-ref:{index}")
            revision = await pool.fetchrow(
                "SELECT id FROM catalog.repo_revisions WHERE repository_id=$1 AND commit_sha=$2",
                repo["id"], commit,
            )
            if revision is None:
                raise ValueError(f"unresolved-evidence:{index}")
            if kind == "revision":
                item = {"kind": "revision", "repository_key": canonical_key, "revision_commit": commit}
            else:
                file_path = str(raw.get("file_path") or "").replace("\\", "/").lstrip("./")
                if not file_path or ".." in file_path.split("/") or len(file_path) > 1024:
                    raise ValueError(f"invalid-evidence-ref:{index}")
                found = await pool.fetchrow(
                    "SELECT 1 FROM catalog.files WHERE repo_revision_id=$1 AND file_path=$2",
                    revision["id"], file_path,
                )
                if found is None:
                    raise ValueError(f"unresolved-evidence:{index}")
                item = {"kind": "file", "repository_key": canonical_key,
                        "file_path": file_path, "revision_commit": commit}
        canonical.append(item)
    canonical.sort(key=lambda item: (
        item["kind"], item["repository_key"],
        item.get("entity_key") or item.get("file_path") or "",
        item.get("revision_commit") or "",
    ))
    serialized = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in canonical]
    if len(serialized) != len(set(serialized)):
        raise ValueError("duplicate-evidence-ref")
    return canonical_key, canonical


def _encode_candidate_cursor(repository_key: str, created_utc: str, entity_key: str) -> str:
    payload = json.dumps({"v": 1, "repository_key": repository_key,
                          "created_utc": created_utc, "entity_key": entity_key},
                         sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_candidate_cursor(cursor: str, repository_key: str) -> tuple[str, uuid.UUID]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if payload.get("v") != 1 or payload.get("repository_key") != repository_key:
            raise ValueError
        return str(payload["created_utc"]), uuid.UUID(payload["entity_key"])
    except (ValueError, KeyError, json.JSONDecodeError):
        raise ValueError("invalid-candidate-cursor") from None


async def list_repo_note_candidates(
    pool: asyncpg.Pool,
    repository_key: str,
    *,
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise ValueError("invalid-limit")
    repo = await pool.fetchrow(
        "SELECT id, repository_key FROM catalog.repositories WHERE lower(repository_key)=lower($1) "
        "ORDER BY (repository_key=$1) DESC, id ASC LIMIT 1", repository_key,
    )
    if repo is None:
        raise ValueError("repository-not-found")
    after_created: str | None = None
    after_key: uuid.UUID | None = None
    if cursor:
        after_created, after_key = _decode_candidate_cursor(cursor, repo["repository_key"])
    rows = await pool.fetch(
        """
        SELECT lr.id, e.entity_key, lr.title, lr.body_text, lr.content_kind,
               lr.evidence_refs, lr.evidence_resolution_errors, lr.confidence,
               lr.created_utc, lr.is_active, lr.verification_status
        FROM memory.learned_records lr
        JOIN catalog.entities e ON e.id=lr.entity_id
        WHERE e.repository_id=$1
          AND (lr.source_kind='operator_note' OR lr.memory_type IN ('note','operator_note'))
          AND (
            (lr.is_active=TRUE AND lr.verification_status='unverified')
            OR lr.content_kind IS NULL OR lr.evidence_refs IS NULL
            OR CASE WHEN jsonb_typeof(lr.evidence_resolution_errors)='array'
                    THEN jsonb_array_length(lr.evidence_resolution_errors)>0 ELSE TRUE END
          )
          AND ($2::timestamptz IS NULL OR (lr.created_utc,e.entity_key)>($2::timestamptz,$3::uuid))
        ORDER BY lr.created_utc ASC, e.entity_key ASC LIMIT $4
        """,
        repo["id"], after_created, after_key, limit + 1,
    )
    page = rows[:limit]
    items = [dict(row) for row in page]
    next_cursor = None
    if len(rows) > limit and page:
        last = page[-1]
        next_cursor = _encode_candidate_cursor(
            repo["repository_key"], last["created_utc"].isoformat(), str(last["entity_key"])
        )
    return {"items": items, "next_cursor": next_cursor, "truncated": next_cursor is not None}


async def _resolve_entity_key_to_id(pool: asyncpg.Pool, entity_key_str: str) -> int | None:
    """Resolve a UUID entity_key string to its PG integer id."""
    row = await pool.fetchrow(
        "SELECT id FROM catalog.entities WHERE entity_key = $1",
        uuid.UUID(entity_key_str),
    )
    return row["id"] if row else None


async def run_proposal(
    repository_key: str,
    memory_type: str,
    title: str,
    body_text: str,
    evidence_entity_key: str,
    scope_entity_key: str,
    confidence: float,
    applicability_mode: str,
    run_id: uuid.UUID,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="run_learned_memory_proposal_workflow",
                status="error",
                error="Missing required dependency: pool.",
            )

        # Step 1: Resolve repository
        repo_row = await pool.fetchrow(
            "SELECT id FROM catalog.repositories WHERE repository_key = $1",
            repository_key,
        )
        if repo_row is None:
            raise ValueError(f"Repository not found: {repository_key}")
        repository_id = repo_row["id"]

        # Step 1.5: Validate memory_type
        if memory_type not in VALID_MEMORY_TYPES:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="run_learned_memory_proposal_workflow",
                status="error",
                error=f"Invalid memory_type: {memory_type}. Must be one of: {', '.join(sorted(VALID_MEMORY_TYPES))}",
            )

        # Step 2: Validate evidence entity exists
        evidence_entity_id = await _resolve_entity_key_to_id(pool, evidence_entity_key)
        if evidence_entity_id is None:
            raise ValueError(f"Evidence entity not found: {evidence_entity_key}")

        # Step 3: Validate scope entity exists
        scope_entity_id = await _resolve_entity_key_to_id(pool, scope_entity_key)
        if scope_entity_id is None:
            raise ValueError(f"Scope entity not found: {scope_entity_key}")

        # Step 4: Look up evidence chunk
        chunk_row = await pool.fetchrow(
            "SELECT id FROM catalog.chunks WHERE entity_id = $1",
            evidence_entity_id,
        )
        if chunk_row is None:
            raise ValueError(f"Evidence entity {evidence_entity_key} has no associated chunk")
        evidence_chunk_id = chunk_row["id"]

        # Step 5: Get current revision
        rev_row = await pool.fetchrow(
            "SELECT id FROM catalog.repo_revisions WHERE repository_id = $1 ORDER BY id DESC LIMIT 1",
            repository_id,
        )
        valid_from_revision_id = rev_row["id"] if rev_row else 0

        # Step 6: Generate entity key
        title_hash = hashlib.sha256(title.encode()).hexdigest()[:16]
        entity_key = learned_record_entity_key(repository_key, memory_type, title_hash)

        # Step 7: Upsert to PG (unverified, not yet in Qdrant/Neo4j)
        learned_record_id = await upsert_learned_record(
            pool=pool,
            entity_key=entity_key,
            entity_id=evidence_entity_id,  # use evidence entity as reference for repo/revision lookup
            scope_entity_id=scope_entity_id,
            memory_type=memory_type,
            title=title,
            body_text=body_text,
            source_kind="agent_proposal",
            confidence=confidence,
            applicability_mode=applicability_mode,
            valid_from_revision_id=valid_from_revision_id,
            evidence_entity_id=evidence_entity_id,
            evidence_chunk_id=evidence_chunk_id,
            verification_status="unverified",
            is_active=True,
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "proposal_created",
            entity_key=str(entity_key),
            learned_record_id=learned_record_id,
        )

        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_proposal_workflow",
            status="success",
            data={
                "proposal_id": str(entity_key),
                "learned_record_id": learned_record_id,
                "verification_status": "unverified",
            },
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("proposal_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_proposal_workflow",
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )


async def run_commit(
    repository_key: str,
    proposal_id: str,
    approval_status: str,
    run_id: uuid.UUID,
    verification_notes: str | None = None,
    supersedes_id: str | None = None,
    content_kind: str | None = None,
    evidence_refs: list[dict[str, Any]] | None = None,
    pool: asyncpg.Pool | None = None,
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_driver: neo4j.AsyncDriver | None = None,
    settings: Settings | None = None,
) -> WorkflowResult:
    start = time.monotonic()

    try:
        if pool is None:
            return WorkflowResult(
                run_id=str(run_id),
                tool_name="run_learned_memory_commit_workflow",
                status="error",
                error="Missing required dependency: pool.",
            )

        if approval_status not in ("approve", "reject", "supersede", "repair-evidence"):
            raise ValueError("invalid-approval-status")

        canonical_repo_row = await pool.fetchrow(
            "SELECT id,repository_key FROM catalog.repositories WHERE lower(repository_key)=lower($1) "
            "ORDER BY (repository_key=$1) DESC,id ASC LIMIT 1", repository_key,
        )
        if canonical_repo_row is None:
            raise ValueError("repository-not-found")
        canonical_repository_key = canonical_repo_row["repository_key"]
        neo4j_warnings: list[str] = []

        async with pool.acquire() as conn:
            async with conn.transaction():
                keys = sorted({proposal_id, *([supersedes_id] if supersedes_id else [])})
                locked: dict[str, asyncpg.Record] = {}
                for key in keys:
                    row = await conn.fetchrow(
                        """
                        SELECT lr.id,lr.entity_id,lr.scope_entity_id,lr.memory_type,lr.title,
                               lr.body_text,lr.confidence,lr.applicability_mode,lr.source_kind,
                               lr.verification_status,lr.is_active,lr.content_kind,lr.evidence_refs,
                               lr.evidence_resolution_errors,e.entity_key,e.repository_id,
                               r.repository_key
                        FROM memory.learned_records lr
                        JOIN catalog.entities e ON e.id=lr.entity_id
                        JOIN catalog.repositories r ON r.id=e.repository_id
                        WHERE e.entity_key=$1 FOR UPDATE OF lr
                        """,
                        uuid.UUID(key),
                    )
                    if row is None:
                        raise ValueError("proposal-not-found")
                    if row["repository_id"] != canonical_repo_row["id"]:
                        raise ValueError("cross-repository-transition")
                    locked[key] = row

                row = locked[proposal_id]
                learned_record_id = row["id"]
                entity_key_str = str(row["entity_key"])
                is_operator = _operator_note(row)
                scope_row = await conn.fetchrow(
                    "SELECT entity_key FROM catalog.entities WHERE id=$1", row["scope_entity_id"]
                )
                scope_ek = str(scope_row["entity_key"]) if scope_row else ""
                evidence_row = await conn.fetchrow(
                    "SELECT e.entity_key FROM catalog.entities e WHERE e.id="
                    "(SELECT evidence_entity_id FROM memory.learned_records WHERE id=$1)",
                    learned_record_id,
                )
                evidence_ek = str(evidence_row["entity_key"]) if evidence_row else None

                async def approve_and_project() -> None:
                    target_status = "human_asserted" if is_operator else "verified"
                    if row["verification_status"] == target_status and bool(row["is_active"]):
                        return
                    if row["verification_status"] != "unverified" or not bool(row["is_active"]):
                        raise ValueError("invalid-approval-transition")
                    if is_operator and (
                        row["content_kind"] not in ALLOWED_CONTENT_KINDS
                        or not row["evidence_refs"] or row["evidence_resolution_errors"]
                    ):
                        raise ValueError("legacy-note-requires-evidence-repair")
                    await conn.execute(
                        "UPDATE memory.learned_records SET verification_status=$2,verification_notes=$3 "
                        "WHERE id=$1", learned_record_id, target_status, verification_notes,
                    )
                    if qdrant_client is not None and settings is not None:
                        await embed_and_upsert_learned_record(
                            client=qdrant_client, entity_key=entity_key_str,
                            body_text=row["body_text"], repository_key=canonical_repository_key,
                            memory_type=row["memory_type"],
                            confidence=float(row["confidence"] or 0.5),
                            applicability_mode=row["applicability_mode"] or "repository",
                            scope_entity_key=scope_ek, settings=settings,
                        )
                    if neo4j_driver is not None:
                        try:
                            await project_learned_rule(
                                driver=neo4j_driver, entity_key=entity_key_str,
                                memory_type=row["memory_type"], title=row["title"],
                                scope_entity_key=scope_ek, evidence_entity_key=evidence_ek,
                            )
                        except Exception:
                            neo4j_warnings.append("neo4j-projection-failed")

                if approval_status == "approve":
                    await approve_and_project()
                    result_data = {"status": "human_asserted" if is_operator else "verified",
                                   "entity_key": entity_key_str}
                elif approval_status == "reject":
                    if row["verification_status"] == "rejected" and not row["is_active"]:
                        result_data = {"status": "rejected", "entity_key": entity_key_str,
                                       "idempotent_retry": True}
                    elif row["verification_status"] == "unverified":
                        await conn.execute(
                            "UPDATE memory.learned_records SET verification_status='rejected',"
                            "verification_notes=$2,is_active=FALSE WHERE id=$1",
                            learned_record_id, verification_notes,
                        )
                        result_data = {"status": "rejected", "entity_key": entity_key_str}
                    else:
                        raise ValueError("invalid-reject-transition")
                    if qdrant_client is not None:
                        try:
                            await deactivate_learned_record_point(qdrant_client, entity_key_str)
                        except Exception:
                            neo4j_warnings.append("qdrant-cleanup-failed")
                elif approval_status == "repair-evidence":
                    if bool(row["is_active"]) or not is_operator or (
                        row["content_kind"] is not None and row["evidence_refs"]
                        and not row["evidence_resolution_errors"]
                    ):
                        raise ValueError("repair-requires-inactive-legacy-note")
                    if content_kind is None or evidence_refs is None:
                        raise ValueError("repair-evidence-fields-required")
                    validate_operational_content(
                        title=row["title"], body_text=row["body_text"],
                        content_kind=content_kind, evidence_refs=evidence_refs,
                    )
                    evidence_repo, canonical_refs = await resolve_evidence_refs(
                        conn, canonical_repository_key, evidence_refs
                    )
                    if evidence_repo != canonical_repository_key:
                        raise ValueError("cross-repository-evidence")
                    await conn.execute(
                        "UPDATE memory.learned_records SET is_active=TRUE,verification_status='unverified',"
                        "content_kind=$2,evidence_refs=$3::jsonb,evidence_resolution_errors='[]'::jsonb "
                        "WHERE id=$1", learned_record_id, content_kind,
                        json.dumps(canonical_refs, sort_keys=True, separators=(",", ":")),
                    )
                    result_data = {"status": "unverified", "entity_key": entity_key_str,
                                   "content_kind": content_kind, "evidence_refs": canonical_refs}
                else:
                    old = locked[supersedes_id]
                    if old["id"] == learned_record_id:
                        raise ValueError("cannot-supersede-self")
                    await approve_and_project()
                    await conn.execute(
                        "UPDATE memory.learned_records SET supersedes_learned_record_id=$2,is_active=FALSE "
                        "WHERE id=$1", old["id"], learned_record_id,
                    )
                    if qdrant_client is not None:
                        try:
                            await deactivate_learned_record_point(qdrant_client, supersedes_id)
                        except Exception:
                            neo4j_warnings.append("qdrant-cleanup-failed")
                    if neo4j_driver is not None:
                        try:
                            from memory_knowledge.projections.learned_memory_neo4j import deactivate_learned_rule
                            await deactivate_learned_rule(neo4j_driver, supersedes_id)
                        except Exception:
                            neo4j_warnings.append("neo4j-cleanup-failed")
                    result_data = {"status": "superseded", "new_entity_key": entity_key_str,
                                   "old_entity_key": supersedes_id}

        if neo4j_warnings:
            result_data["cleanup_warnings"] = sorted(set(neo4j_warnings))

        duration_ms = int((time.monotonic() - start) * 1000)
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_commit_workflow",
            status="success",
            data=result_data,
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.error("commit_failed", error=str(exc))
        return WorkflowResult(
            run_id=str(run_id),
            tool_name="run_learned_memory_commit_workflow",
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
