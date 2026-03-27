from __future__ import annotations

from pydantic import BaseModel


class CodeChunkPayload(BaseModel):
    entity_key: str
    repository_key: str
    commit_sha: str
    branch_name: str
    file_path: str
    symbol_name: str | None = None
    chunk_type: str
    is_active: bool
    retrieval_surface: str
    content_kind: str = "code_chunk"


class SummaryPayload(BaseModel):
    entity_key: str
    repository_key: str
    commit_sha: str
    summary_level: str
    is_active: bool
    content_kind: str = "summary"


class LearnedMemoryPayload(BaseModel):
    entity_key: str
    repository_key: str
    memory_type: str
    confidence: float
    applicability_mode: str
    scope_entity_key: str
    is_active: bool
    content_kind: str = "learned_rule"
