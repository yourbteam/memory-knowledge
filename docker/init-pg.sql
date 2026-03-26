-- ============================================================================
-- Memory Knowledge — PostgreSQL Init Script
-- Creates all schemas, tables, indexes, and seed data for Phase 1
-- ============================================================================

-- Schemas
CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS memory;
CREATE SCHEMA IF NOT EXISTS routing;
CREATE SCHEMA IF NOT EXISTS ops;

-- Enums
CREATE TYPE catalog.surface_type_enum AS ENUM (
    'live_branch', 'release_branch', 'pinned_commit'
);

-- ============================================================================
-- CATALOG schema — Phase 1 active tables
-- ============================================================================

CREATE TABLE catalog.repositories (
    id          BIGSERIAL PRIMARY KEY,
    repository_key VARCHAR(255) NOT NULL UNIQUE,
    name        VARCHAR(255) NOT NULL,
    origin_url  TEXT,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.repo_revisions (
    id             BIGSERIAL PRIMARY KEY,
    repository_id  BIGINT NOT NULL REFERENCES catalog.repositories(id),
    commit_sha     VARCHAR(40) NOT NULL,
    branch_name    VARCHAR(255),
    parent_sha     VARCHAR(40),
    committed_utc  TIMESTAMPTZ,
    created_utc    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.branch_heads (
    id               BIGSERIAL PRIMARY KEY,
    repository_id    BIGINT NOT NULL REFERENCES catalog.repositories(id),
    branch_name      VARCHAR(255) NOT NULL,
    repo_revision_id BIGINT NOT NULL REFERENCES catalog.repo_revisions(id),
    updated_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repository_id, branch_name)
);

CREATE TABLE catalog.retrieval_surfaces (
    id               BIGSERIAL PRIMARY KEY,
    repository_id    BIGINT NOT NULL REFERENCES catalog.repositories(id),
    surface_type     catalog.surface_type_enum NOT NULL,
    branch_name      VARCHAR(255),
    commit_sha       VARCHAR(40),
    repo_revision_id BIGINT NOT NULL REFERENCES catalog.repo_revisions(id),
    is_default       BOOLEAN NOT NULL DEFAULT FALSE,
    created_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.entities (
    id               BIGSERIAL PRIMARY KEY,
    entity_key       UUID NOT NULL UNIQUE,
    entity_type      VARCHAR(50) NOT NULL,
    repository_id    BIGINT NOT NULL REFERENCES catalog.repositories(id),
    repo_revision_id BIGINT NOT NULL REFERENCES catalog.repo_revisions(id),
    external_hash    VARCHAR(64),
    created_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.files (
    id               BIGSERIAL PRIMARY KEY,
    entity_id        BIGINT NOT NULL REFERENCES catalog.entities(id),
    repo_revision_id BIGINT NOT NULL REFERENCES catalog.repo_revisions(id),
    file_path        TEXT NOT NULL,
    language         VARCHAR(50),
    size_bytes       BIGINT,
    checksum         VARCHAR(64),
    created_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.symbols (
    id          BIGSERIAL PRIMARY KEY,
    entity_id   BIGINT NOT NULL REFERENCES catalog.entities(id),
    file_id     BIGINT NOT NULL REFERENCES catalog.files(id),
    symbol_name VARCHAR(500) NOT NULL,
    symbol_kind VARCHAR(50) NOT NULL,
    line_start  INT,
    line_end    INT,
    signature   TEXT,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.chunks (
    id           BIGSERIAL PRIMARY KEY,
    entity_id    BIGINT NOT NULL REFERENCES catalog.entities(id),
    file_id      BIGINT NOT NULL REFERENCES catalog.files(id),
    title        VARCHAR(500),
    content_text TEXT NOT NULL,
    content_tsv  TSVECTOR,
    chunk_type   VARCHAR(50),
    line_start   INT,
    line_end     INT,
    checksum     VARCHAR(64),
    created_utc  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- ROUTING schema
-- ============================================================================

CREATE TABLE routing.route_policies (
    id                      BIGSERIAL PRIMARY KEY,
    policy_name             VARCHAR(255) NOT NULL,
    prompt_class            VARCHAR(50) NOT NULL,
    first_store             VARCHAR(50),
    second_store            VARCHAR(50),
    third_store             VARCHAR(50),
    allow_fanout            BOOLEAN NOT NULL DEFAULT FALSE,
    allow_graph_expansion   BOOLEAN NOT NULL DEFAULT FALSE,
    semantic_assist_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    confidence_threshold    NUMERIC(3,2) DEFAULT 0.50,
    fusion_strategy         VARCHAR(50),
    rerank_strategy         VARCHAR(50),
    created_utc             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE routing.route_executions (
    id                   BIGSERIAL PRIMARY KEY,
    run_id               UUID NOT NULL,
    repository_id        BIGINT REFERENCES catalog.repositories(id),
    prompt_text          TEXT,
    prompt_class         VARCHAR(50),
    route_policy_id      BIGINT REFERENCES routing.route_policies(id),
    first_store_queried  VARCHAR(50),
    stores_queried       VARCHAR(50)[],
    fanout_used          BOOLEAN DEFAULT FALSE,
    graph_expansion_used BOOLEAN DEFAULT FALSE,
    rerank_strategy      VARCHAR(50),
    result_count         INT,
    duration_ms          INT,
    created_utc          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- OPS schema
-- ============================================================================

CREATE TABLE ops.ingestion_runs (
    id             BIGSERIAL PRIMARY KEY,
    repository_id  BIGINT NOT NULL REFERENCES catalog.repositories(id),
    commit_sha     VARCHAR(40),
    branch_name    VARCHAR(255),
    run_type       VARCHAR(50),
    status         VARCHAR(50) NOT NULL DEFAULT 'pending',
    started_utc    TIMESTAMPTZ,
    completed_utc  TIMESTAMPTZ,
    error_text     TEXT
);

-- ============================================================================
-- Forward-compatibility DDL (created but not active in Phase 1)
-- ============================================================================

CREATE TABLE catalog.summaries (
    id            BIGSERIAL PRIMARY KEY,
    entity_id     BIGINT REFERENCES catalog.entities(id),
    summary_level VARCHAR(50),
    summary_text  TEXT,
    created_utc   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.symbol_calls_symbol (
    id                BIGSERIAL PRIMARY KEY,
    caller_symbol_id  BIGINT REFERENCES catalog.symbols(id),
    callee_symbol_id  BIGINT REFERENCES catalog.symbols(id),
    created_utc       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE catalog.file_imports_file (
    id                BIGSERIAL PRIMARY KEY,
    importer_file_id  BIGINT REFERENCES catalog.files(id),
    imported_file_id  BIGINT REFERENCES catalog.files(id),
    created_utc       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE memory.learned_records (
    id                            BIGSERIAL PRIMARY KEY,
    entity_id                     BIGINT REFERENCES catalog.entities(id),
    scope_entity_id               BIGINT REFERENCES catalog.entities(id),
    memory_type                   VARCHAR(50),
    title                         VARCHAR(500),
    body_text                     TEXT,
    body_tsv                      TSVECTOR,
    source_kind                   VARCHAR(50),
    confidence                    NUMERIC(3,2),
    applicability_mode            VARCHAR(50),
    valid_from_revision_id        BIGINT REFERENCES catalog.repo_revisions(id),
    valid_to_revision_id          BIGINT REFERENCES catalog.repo_revisions(id),
    evidence_entity_id            BIGINT REFERENCES catalog.entities(id),
    evidence_chunk_id             BIGINT REFERENCES catalog.chunks(id),
    supersedes_learned_record_id  BIGINT REFERENCES memory.learned_records(id),
    verification_status           VARCHAR(50),
    verification_notes            TEXT,
    is_active                     BOOLEAN NOT NULL DEFAULT TRUE,
    created_utc                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE memory.working_sessions (
    id              BIGSERIAL PRIMARY KEY,
    repository_id   BIGINT REFERENCES catalog.repositories(id),
    session_key     UUID NOT NULL UNIQUE,
    started_utc     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_utc       TIMESTAMPTZ
);

CREATE TABLE memory.working_observations (
    id               BIGSERIAL PRIMARY KEY,
    session_id       BIGINT REFERENCES memory.working_sessions(id),
    entity_id        BIGINT REFERENCES catalog.entities(id),
    observation_type VARCHAR(50),
    observation_text TEXT,
    created_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE routing.route_feedback (
    id                 BIGSERIAL PRIMARY KEY,
    route_execution_id BIGINT REFERENCES routing.route_executions(id),
    usefulness_score   NUMERIC(3,2),
    precision_score    NUMERIC(3,2),
    expansion_needed   BOOLEAN,
    notes              TEXT,
    created_utc        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ops.ingestion_run_items (
    id               BIGSERIAL PRIMARY KEY,
    ingestion_run_id BIGINT REFERENCES ops.ingestion_runs(id),
    entity_id        BIGINT REFERENCES catalog.entities(id),
    item_type        VARCHAR(50),
    status           VARCHAR(50),
    error_text       TEXT,
    created_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ops.job_manifests (
    id               BIGSERIAL PRIMARY KEY,
    run_id           UUID NOT NULL,
    job_id           UUID NOT NULL UNIQUE,
    repository_key   VARCHAR(255) NOT NULL,
    commit_sha       VARCHAR(40),
    branch_name      VARCHAR(255),
    tool_name        VARCHAR(100) NOT NULL,
    state_code       VARCHAR(50) NOT NULL DEFAULT 'pending',
    job_type         VARCHAR(50) NOT NULL,
    attempt_number   INT NOT NULL DEFAULT 1,
    checkpoint_data  JSONB,
    started_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_utc    TIMESTAMPTZ,
    error_code       VARCHAR(50),
    error_text       TEXT,
    correlation_id   VARCHAR(255),
    created_utc      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX idx_chunks_content_tsv ON catalog.chunks USING GIN (content_tsv);
CREATE INDEX idx_chunks_entity_id ON catalog.chunks (entity_id);
CREATE INDEX idx_chunks_file_id ON catalog.chunks (file_id);
CREATE INDEX idx_files_repo_revision_id ON catalog.files (repo_revision_id);
CREATE INDEX idx_entities_repository_id ON catalog.entities (repository_id);
CREATE INDEX idx_job_manifests_run_id ON ops.job_manifests (run_id);
CREATE INDEX idx_job_manifests_repo_state ON ops.job_manifests (repository_key, state_code);

-- ============================================================================
-- Unique constraints for upsert idempotency
-- ============================================================================

ALTER TABLE catalog.repo_revisions ADD CONSTRAINT uq_repo_revisions_repo_commit UNIQUE (repository_id, commit_sha);
ALTER TABLE catalog.files ADD CONSTRAINT uq_files_revision_path UNIQUE (repo_revision_id, file_path);
ALTER TABLE catalog.symbols ADD CONSTRAINT uq_symbols_entity UNIQUE (entity_id);
ALTER TABLE catalog.chunks ADD CONSTRAINT uq_chunks_entity UNIQUE (entity_id);
ALTER TABLE catalog.retrieval_surfaces ADD CONSTRAINT uq_retrieval_surfaces UNIQUE NULLS NOT DISTINCT (repository_id, surface_type, branch_name);

-- Phase 3 learned memory constraints
ALTER TABLE memory.learned_records ALTER COLUMN evidence_entity_id SET NOT NULL;
ALTER TABLE memory.learned_records ALTER COLUMN evidence_chunk_id SET NOT NULL;
ALTER TABLE memory.learned_records ADD CONSTRAINT uq_learned_records_entity UNIQUE (entity_id);
CREATE INDEX idx_learned_records_body_tsv ON memory.learned_records USING GIN (body_tsv);

-- Phase 5 edge table constraints
ALTER TABLE catalog.file_imports_file ADD CONSTRAINT uq_file_imports UNIQUE (importer_file_id, imported_file_id);
ALTER TABLE catalog.symbol_calls_symbol ADD CONSTRAINT uq_symbol_calls UNIQUE (caller_symbol_id, callee_symbol_id);

-- Phase 6 summary constraints and indexes
ALTER TABLE catalog.summaries ADD COLUMN IF NOT EXISTS summary_tsv TSVECTOR;
CREATE INDEX IF NOT EXISTS idx_summaries_tsv ON catalog.summaries USING GIN (summary_tsv);
ALTER TABLE catalog.summaries ADD CONSTRAINT uq_summaries UNIQUE (entity_id, summary_level);

-- ============================================================================
-- Seed data — default route policies
-- ============================================================================

INSERT INTO routing.route_policies
    (policy_name, prompt_class, first_store, second_store, third_store,
     allow_fanout, allow_graph_expansion, semantic_assist_enabled,
     confidence_threshold, fusion_strategy, rerank_strategy)
VALUES
    ('exact_lookup_default',      'exact_lookup',      'postgres', 'neo4j',   'qdrant',  FALSE, FALSE, FALSE, 0.80, 'score_merge', 'score_sort'),
    ('conceptual_lookup_default', 'conceptual_lookup', 'qdrant',   'postgres', 'neo4j',  FALSE, TRUE,  TRUE,  0.50, 'score_merge', 'score_sort'),
    ('impact_analysis_default',   'impact_analysis',   'neo4j',    'postgres', 'qdrant', TRUE,  TRUE,  FALSE, 0.60, 'score_merge', 'score_sort'),
    ('pattern_search_default',    'pattern_search',    'qdrant',   'postgres', 'neo4j',  FALSE, FALSE, TRUE,  0.50, 'score_merge', 'score_sort'),
    ('decision_history_default',  'decision_history',  'postgres', 'qdrant',   'neo4j',  FALSE, FALSE, TRUE,  0.50, 'score_merge', 'score_sort'),
    ('mixed_default',             'mixed',             'postgres', 'qdrant',   'neo4j',  TRUE,  TRUE,  TRUE,  0.40, 'score_merge', 'score_sort');
