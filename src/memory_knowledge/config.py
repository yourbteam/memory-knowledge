from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # PostgreSQL
    database_url: str
    pg_pool_min_size: int = 5
    pg_pool_max_size: int = 20

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str | None = None

    # Neo4j
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_max_pool_size: int = 50

    # Auth
    auth_mode: Literal["api_key", "codex"] = "api_key"
    codex_auth_path: str = "~/.codex/auth.json"

    # OpenAI
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Ingestion
    repo_clone_base_path: str = "/tmp/memory-knowledge/repos"

    # Server
    server_port: int = 8000


_settings: Settings | None = None


def init_settings(settings: Settings) -> None:
    global _settings
    _settings = settings


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings not initialized")
    return _settings
