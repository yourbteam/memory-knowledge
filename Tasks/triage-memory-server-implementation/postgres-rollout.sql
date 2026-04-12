BEGIN;

CREATE TABLE IF NOT EXISTS ops.triage_cases (
    id BIGSERIAL PRIMARY KEY,
    triage_case_id UUID NOT NULL UNIQUE,
    repository_id BIGINT NOT NULL REFERENCES catalog.repositories(id) ON DELETE CASCADE,
    prompt_text TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    request_kind VARCHAR(100) NOT NULL,
    execution_mode VARCHAR(100) NOT NULL,
    knowledge_mode VARCHAR(100) NOT NULL,
    selected_workflow_name VARCHAR(255),
    suggested_workflows JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_run_action VARCHAR(100),
    requires_clarification BOOLEAN NOT NULL DEFAULT FALSE,
    clarifying_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    fallback_route VARCHAR(255),
    confidence DOUBLE PRECISION,
    reasoning_summary TEXT,
    project_key VARCHAR(255),
    feature_key VARCHAR(255),
    task_key VARCHAR(255),
    actor_email TEXT,
    policy_version VARCHAR(255),
    workflow_catalog_version VARCHAR(255),
    decision_source VARCHAR(100),
    matched_case_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ops.triage_case_feedback (
    id BIGSERIAL PRIMARY KEY,
    triage_case_id UUID NOT NULL REFERENCES ops.triage_cases(triage_case_id) ON DELETE CASCADE,
    outcome_status VARCHAR(100) NOT NULL,
    successful_execution BOOLEAN,
    human_override BOOLEAN,
    correction_reason TEXT,
    corrected_request_kind VARCHAR(100),
    corrected_execution_mode VARCHAR(100),
    corrected_selected_workflow_name VARCHAR(255),
    feedback_notes TEXT,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_triage_cases_repository_created
    ON ops.triage_cases(repository_id, created_utc DESC);

CREATE INDEX IF NOT EXISTS ix_triage_cases_project_feature
    ON ops.triage_cases(project_key, feature_key);

CREATE INDEX IF NOT EXISTS ix_triage_cases_request_kind
    ON ops.triage_cases(request_kind);

CREATE INDEX IF NOT EXISTS ix_triage_cases_workflow_action
    ON ops.triage_cases(selected_workflow_name, selected_run_action);

CREATE INDEX IF NOT EXISTS ix_triage_cases_policy_version
    ON ops.triage_cases(policy_version);

CREATE INDEX IF NOT EXISTS ix_triage_case_feedback_case_created
    ON ops.triage_case_feedback(triage_case_id, created_utc DESC, id DESC);

COMMIT;
