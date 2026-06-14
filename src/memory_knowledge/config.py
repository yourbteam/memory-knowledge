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
    pg_ssl_ca_path: str = ""  # CA bundle for full verification (e.g. Supabase root CA)
    pg_ssl_insecure: bool = False  # opt-out: encrypt without cert verification (NOT recommended)
    pg_command_timeout: int = 30
    # Recycle idle pooled connections before Supabase/PgBouncer silently drops
    # them, so the first query after an idle period (hourly/weekly schedulers)
    # doesn't fail with ConnectionDoesNotExistError (mirrors the Neo4j fix).
    pg_max_inactive_connection_lifetime_seconds: float = 300.0

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str | None = None
    # Bound every Qdrant HTTP call; an unbounded client hangs startup and
    # queries indefinitely on a network blip (the ResponseHandlingException class).
    qdrant_timeout_seconds: float = 60.0

    # Neo4j
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_max_pool_size: int = 50
    # Connection liveness — Aura drops idle connections; recycle/health-check
    # them so a stale pooled connection doesn't abort ingestion (SessionExpired).
    neo4j_liveness_check_timeout_seconds: float = 30.0
    neo4j_max_connection_lifetime_seconds: float = 300.0
    neo4j_connection_acquisition_timeout_seconds: float = 60.0

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
    embedding_provider: Literal["local", "openai"] = "local"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dimensions: int = 768
    completion_model: str = "gpt-4o"
    max_completion_tokens: int = 4096

    # Advisory Q&A retrieval: minimum cosine similarity to surface a suggestion.
    # Measured intra-repo near-duplicate scores are ~0.49–0.60; 0.65 over-filtered.
    qa_search_min_similarity: float = 0.45

    # Advisory Q&A lexical fallback: minimum normalized-token Jaccard overlap between the asked
    # question and a candidate question for the (unfloored) full-text fallback to surface it.
    # Keeps near-exact re-asks, drops loose token-overlap junk when little Q&A is ingested.
    qa_lexical_min_overlap: float = 0.6

    # Ingestion
    repo_clone_base_path: str = "/tmp/memory-knowledge/repos"
    generate_summaries: bool = True
    supported_languages: list[str] = ["python", "csharp", "sql", "typescript", "php"]
    max_import_size_mb: int = 250
    github_access_token: str | None = None
    github_https_username: str = "x-access-token"
    github_app_config_path: str = "~/.codex/.github/app-config.json"
    kv_github_app_config_secret_name: str = "github-app-config"

    # Freshness
    max_surface_age_hours: int = 168  # 7 days

    # Compaction / GC
    compaction_enabled: bool = False
    compaction_dry_run_default: bool = True

    # Ingestion freshness scheduler
    ingestion_scheduler_enabled: bool = False
    ingestion_scheduler_interval_seconds: int = 3600
    ingestion_scheduler_repo_allowlist: str = ""  # CSV; empty = all repos with origin_url (minus test prefixes)
    ingestion_scheduler_max_per_tick: int = 5  # bounds enqueues per tick, not the cheap ls-remote checks

    # Maintenance scheduler (audit + compaction)
    maintenance_scheduler_enabled: bool = False
    maintenance_interval_seconds: int = 604800  # weekly

    # Job orchestration
    max_job_retries: int = 3
    job_retry_delay_seconds: float = 5.0
    job_orphan_timeout_seconds: int = 3600
    # Retry/dead-letter sweep: promote failed jobs back to 'retrying' (until the
    # attempt cap, then 'dead_letter') so transient failures self-heal instead of
    # stranding a repo stale forever. Backoff lets the transient condition clear.
    job_retry_backoff_seconds: float = 60.0
    job_retry_sweep_enabled: bool = True
    # Serialize dispatch: the shared B3 plan cannot run concurrent heavy
    # ingestions (full re-ingest of a large repo OOMs / trips health checks).
    job_dispatcher_max_concurrent: int = 1
    job_dispatcher_poll_interval_seconds: float = 15.0
    # Recover jobs left in 'running' by a crashed/restarted container.
    reclaim_stale_running_jobs_on_start: bool = True

    # HTTP
    cors_allowed_origins: str = "*"

    # Server
    server_port: int = 8000
    log_level: str = "INFO"
    environment: str = "development"

    # Data mode
    data_mode: Literal["local", "remote"] = "local"
    pg_mode: Literal["local", "remote"] | None = None
    qdrant_mode: Literal["local", "remote"] | None = None
    neo4j_mode: Literal["local", "remote"] | None = None

    # Remote safety guards
    allow_remote_writes: bool = False
    allow_remote_rebuilds: bool = False

    # Azure KV secret names for DB credentials
    kv_pg_secret_name: str = "db-postgres-url"
    kv_qdrant_secret_name: str = "db-qdrant-apikey"
    kv_neo4j_secret_name: str = "db-neo4j-password"

    def effective_mode(self, db: str) -> str:
        """Resolve effective mode for a specific database."""
        override = getattr(self, f"{db}_mode", None)
        return override if override is not None else self.data_mode

    def is_any_remote(self) -> bool:
        """True if any database is in remote mode."""
        return any(self.effective_mode(db) == "remote" for db in ("pg", "qdrant", "neo4j"))


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
