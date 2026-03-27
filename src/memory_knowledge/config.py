from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # PostgreSQL
    database_url: str
    pg_pool_min_size: int = 5
    pg_pool_max_size: int = 20
    pg_ssl: bool = False
    pg_command_timeout: int = 30

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str | None = None

    # Neo4j
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_max_pool_size: int = 50

    # Auth
    auth_mode: Literal["api_key", "codex"] = "codex"
    codex_auth_path: str = "~/.codex/auth.json"
    mcp_api_key: str | None = None  # Bearer token for MCP endpoint auth

    # Codex token refresh
    azure_keyvault_name: str = ""  # empty = KV disabled
    codex_refresh_enabled: bool = True
    codex_refresh_after_days: int = 6
    codex_check_interval: int = 300  # seconds between staleness checks
    codex_daily_refresh_hour: int = 5  # UTC hour for daily refresh
    codex_kv_writeback_enabled: bool = True

    # OpenAI
    openai_api_key: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    completion_model: str = "gpt-4o"
    max_completion_tokens: int = 4096

    # Ingestion
    repo_clone_base_path: str = "/tmp/memory-knowledge/repos"
    generate_summaries: bool = True
    supported_languages: list[str] = ["python"]
    max_import_size_mb: int = 50

    # Freshness
    max_surface_age_hours: int = 168  # 7 days

    # Job orchestration
    max_job_retries: int = 3
    job_retry_delay_seconds: float = 5.0

    # HTTP
    cors_allowed_origins: str = "*"

    # Server
    server_port: int = 8000
    log_level: str = "INFO"
    environment: str = "development"


_settings: Settings | None = None


def init_settings(settings: Settings) -> None:
    global _settings
    _settings = settings


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings not initialized")
    return _settings


# Language → file extension mapping
LANGUAGE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "typescript": [".ts", ".tsx", ".js", ".jsx"],
    "csharp": [".cs"],
    "php": [".php"],
    "sql": [".sql"],
}


def get_supported_extensions(languages: list[str]) -> set[str]:
    """Flatten configured languages into a set of file extensions."""
    extensions: set[str] = set()
    for lang in languages:
        extensions.update(LANGUAGE_EXTENSIONS.get(lang, []))
    return extensions
