from __future__ import annotations

import uuid

# Fixed namespace for all entity key generation. NEVER change this value.
NAMESPACE_MK = uuid.UUID("b7e15163-2a0e-4e29-8f3a-d4b612c8a1f7")


def file_entity_key(repo_key: str, commit_sha: str, file_path: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE_MK, f"{repo_key}:{commit_sha}:{file_path}")


def symbol_entity_key(
    repo_key: str,
    commit_sha: str,
    file_path: str,
    symbol_name: str,
    symbol_kind: str,
) -> uuid.UUID:
    return uuid.uuid5(
        NAMESPACE_MK,
        f"{repo_key}:{commit_sha}:{file_path}:{symbol_name}:{symbol_kind}",
    )


def chunk_entity_key(
    repo_key: str, commit_sha: str, file_path: str, chunk_index: int
) -> uuid.UUID:
    return uuid.uuid5(
        NAMESPACE_MK, f"{repo_key}:{commit_sha}:{file_path}:{chunk_index}"
    )


def learned_record_entity_key(
    repo_key: str, memory_type: str, title_hash: str
) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE_MK, f"{repo_key}:{memory_type}:{title_hash}")


def summary_entity_key(
    repo_key: str,
    commit_sha: str,
    entity_key_str: str,
    summary_level: str,
) -> uuid.UUID:
    return uuid.uuid5(
        NAMESPACE_MK,
        f"{repo_key}:{commit_sha}:{entity_key_str}:summary:{summary_level}",
    )
