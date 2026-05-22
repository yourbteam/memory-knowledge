from pathlib import Path


MIGRATION = Path("migrations/versions/016_mawf_contract.py")
LEASE_MIGRATION = Path("migrations/versions/017_mawf_task_execution_leases.py")
ARTIFACT_KEY_MIGRATION = Path("migrations/versions/018_mawf_artifact_ref_keys.py")
USER_WORKFLOW_RUN_MIGRATION = Path("migrations/versions/019_mawf_workflow_runs_by_user.py")
RECOVERABLE_WORKFLOW_RUN_MIGRATION = Path("migrations/versions/020_mawf_recoverable_workflow_runs.py")
EXTERNAL_TASK_ID_MIGRATION = Path("migrations/versions/021_mawf_external_task_id.py")
TASK_ARTIFACT_BRANCH_MIGRATION = Path("migrations/versions/022_mawf_task_artifact_branch_metadata.py")
ARTIFACT_KEY_HANDOFF = Path("docs/MCP_AGENTS_WORKFLOW_ARTIFACT_REF_KEYS_HANDOFF.md")


def test_mawf_migration_contains_required_schema_objects():
    text = MIGRATION.read_text()
    required = [
        "ADD COLUMN IF NOT EXISTS mawf_code",
        "ux_reference_values_type_mawf_code",
        "CREATE TABLE IF NOT EXISTS core.users",
        "CREATE TABLE IF NOT EXISTS ops.mawf_prompts",
        "CREATE TABLE IF NOT EXISTS planning.mawf_artifact_refs",
        "ALTER TABLE planning.projects ADD COLUMN IF NOT EXISTS mawf_project_key",
        "ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS mawf_repository_id",
        "ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS provider",
        "ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS owner",
        "ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS repo_name",
        "ALTER TABLE catalog.repositories ADD COLUMN IF NOT EXISTS status_id",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS mawf_task_id",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS owner_user_id",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS prompt_id",
        "ALTER TABLE planning.tasks ADD COLUMN IF NOT EXISTS task_ledger_ref",
        "CONSTRAINT uq_mawf_artifact_refs_task_role UNIQUE",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_migration_seeds_catalog_values_and_type_enforcement():
    text = MIGRATION.read_text()
    required = [
        "'USER_ROLE'",
        "'USER_STATUS'",
        "'REPOSITORY_STATUS'",
        "'ARTIFACT_ROLE'",
        "'ARTIFACT_PERSIST_STATUS'",
        "'TASK_FAILED'",
        "core.enforce_reference_value_types",
        "trg_users_reference_types",
        "trg_projects_reference_types",
        "trg_repositories_reference_types",
        "trg_tasks_reference_types",
        "trg_mawf_artifact_refs_reference_types",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_migration_does_not_create_duplicate_public_core_tables():
    text = MIGRATION.read_text()
    forbidden = [
        "CREATE TABLE users",
        "CREATE TABLE projects",
        "CREATE TABLE repositories",
        "CREATE TABLE tasks",
        "CREATE TABLE public.users",
        "CREATE TABLE public.projects",
        "CREATE TABLE public.repositories",
        "CREATE TABLE public.tasks",
    ]
    for snippet in forbidden:
        assert snippet not in text


def test_mawf_lease_migration_contains_required_schema_objects():
    text = LEASE_MIGRATION.read_text()
    required = [
        "TASK_EXECUTION_LEASE_STATUS",
        "TASK_EXECUTION_LEASE_RELEASE_REASON",
        "'active'",
        "'released'",
        "'expired'",
        "'failed'",
        "'completed'",
        "'operator_cancelled'",
        "'server_shutdown'",
        "'stale_reclaimed'",
        "CREATE TABLE IF NOT EXISTS ops.mawf_task_execution_leases",
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid()",
        "task_id BIGINT NOT NULL REFERENCES planning.tasks(id)",
        "workflow_run_id BIGINT NULL REFERENCES ops.workflow_runs(id)",
        "lease_token UUID NOT NULL UNIQUE DEFAULT gen_random_uuid()",
        "owner_user_id UUID NULL REFERENCES core.users(id)",
        "owner_instance_id TEXT NOT NULL",
        "status_value_id BIGINT NOT NULL REFERENCES core.reference_values(id)",
        "release_reason_value_id BIGINT NULL REFERENCES core.reference_values(id)",
        "metadata_json JSONB NULL",
        "ux_mawf_task_execution_leases_open_task",
        "ix_mawf_task_execution_leases_task_id",
        "ix_mawf_task_execution_leases_workflow_run_id",
        "ix_mawf_task_execution_leases_owner_user_id",
        "ix_mawf_task_execution_leases_status_expires",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_lease_migration_enforces_reference_and_workflow_task_invariants():
    text = LEASE_MIGRATION.read_text()
    required = [
        "core.enforce_reference_value_types",
        "trg_mawf_task_execution_leases_reference_types",
        "'status_value_id', 'TASK_EXECUTION_LEASE_STATUS'",
        "'release_reason_value_id', 'TASK_EXECUTION_LEASE_RELEASE_REASON'",
        "ops.enforce_mawf_task_execution_lease_workflow_task",
        "planning.task_workflow_runs",
        "RAISE EXCEPTION 'workflow_run_id % is not linked to task_id %'",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_lease_migration_stays_coordination_only():
    text = LEASE_MIGRATION.read_text().lower()
    forbidden = [
        "create table if not exists ops.mawf_phase",
        "create table if not exists ops.phase",
        "workflow_ledger",
        "phase_ledger",
        "artifact_content",
        "polling_state",
    ]
    for snippet in forbidden:
        assert snippet not in text


def test_mawf_artifact_key_migration_contains_minimal_expansion():
    text = ARTIFACT_KEY_MIGRATION.read_text()
    required = [
        "ALTER TABLE planning.mawf_artifact_refs ADD COLUMN IF NOT EXISTS artifact_key TEXT",
        "SET artifact_key = COALESCE(role.mawf_code, role.internal_code)",
        "ALTER COLUMN artifact_key SET NOT NULL",
        "DROP CONSTRAINT IF EXISTS uq_mawf_artifact_refs_task_role",
        "ux_mawf_artifact_refs_task_artifact_key",
        "ON planning.mawf_artifact_refs(mawf_task_id, artifact_key)",
        "ix_mawf_artifact_refs_task_role",
        "workflow_ledger",
        "workflow_state",
        "phase_ledger",
        "telemetry_jsonl",
        "telemetry_summary",
        "generated_artifact",
        "feedback_payload",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_artifact_key_migration_stays_reference_only():
    text = ARTIFACT_KEY_MIGRATION.read_text().lower()
    forbidden = [
        "workflow_run_id",
        "phase_id",
        "metadata_json",
        "content_text",
        "artifact_content",
        "create table if not exists ops.mawf_phase",
        "create table if not exists ops.phase",
        "execution_history",
    ]
    for snippet in forbidden:
        assert snippet not in text


def test_mawf_task_artifact_branch_migration_follows_external_task_id_and_adds_nullable_columns():
    text = TASK_ARTIFACT_BRANCH_MIGRATION.read_text()
    required = [
        'down_revision = "021_mawf_external_task_id"',
        "ALTER TABLE planning.tasks",
        "ADD COLUMN IF NOT EXISTS task_artifact_branch TEXT",
        "ALTER TABLE planning.mawf_artifact_refs",
        "ADD COLUMN IF NOT EXISTS artifact_branch TEXT",
        "ADD COLUMN IF NOT EXISTS artifact_key TEXT",
        "ALTER COLUMN artifact_key DROP NOT NULL",
        "SET artifact_key = NULL",
        "ar.artifact_key = COALESCE(role.mawf_code, role.internal_code)",
        "OR ar.artifact_key = role.internal_code",
    ]
    for snippet in required:
        assert snippet in text
    assert "ALTER COLUMN artifact_key SET NOT NULL" not in text


def test_mawf_task_artifact_branch_migration_replaces_artifact_ref_uniqueness():
    text = TASK_ARTIFACT_BRANCH_MIGRATION.read_text()
    required = [
        "DROP INDEX IF EXISTS planning.ux_mawf_artifact_refs_task_artifact_key",
        "DROP CONSTRAINT IF EXISTS uq_mawf_artifact_refs_task_role",
        "ux_mawf_artifact_refs_task_artifact_key_keyed",
        "ON planning.mawf_artifact_refs(mawf_task_id, artifact_key)",
        "WHERE artifact_key IS NOT NULL",
        "ux_mawf_artifact_refs_task_role_legacy",
        "ON planning.mawf_artifact_refs(mawf_task_id, role_id)",
        "WHERE artifact_key IS NULL",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_task_artifact_branch_downgrade_is_best_effort_without_key_fabrication():
    text = TASK_ARTIFACT_BRANCH_MIGRATION.read_text()
    required = [
        "DROP INDEX IF EXISTS planning.ux_mawf_artifact_refs_task_artifact_key_keyed",
        "DROP INDEX IF EXISTS planning.ux_mawf_artifact_refs_task_role_legacy",
        "DROP COLUMN IF EXISTS artifact_branch",
        "DROP COLUMN IF EXISTS task_artifact_branch",
        "do not fabricate role-derived artifact_key values",
        "pre-022 non-null key semantic contract",
    ]
    for snippet in required:
        assert snippet in text
    downgrade_text = text.split("def downgrade", 1)[1]
    assert "COALESCE(role.mawf_code, role.internal_code)" not in downgrade_text
    assert "ALTER COLUMN artifact_key SET NOT NULL" not in downgrade_text


def test_artifact_key_handoff_marks_old_key_defaults_historical():
    text = ARTIFACT_KEY_HANDOFF.read_text()
    assert "pre-`022` historical deployment evidence" in text
    assert "omitted or blank `artifact_key` must remain `NULL`" in text
    assert "stores and returns `artifact_key: null`" in text
    assert "defaults it to `role_code`" not in text
    assert "defaults to `role_code`" not in text


def test_mawf_user_workflow_run_migration_contains_required_index_support():
    text = USER_WORKFLOW_RUN_MIGRATION.read_text()
    required = [
        "ALTER TABLE ops.workflow_runs",
        "ADD COLUMN IF NOT EXISTS updated_utc TIMESTAMPTZ",
        "SET updated_utc = COALESCE(completed_utc, started_utc, NOW())",
        "ALTER COLUMN updated_utc SET DEFAULT NOW()",
        "ALTER COLUMN updated_utc SET NOT NULL",
        "RUN_WAITING_FOR_FEEDBACK",
        "waiting_for_feedback",
        "RUN_RESUME_PENDING",
        "resume_pending",
        "ix_workflow_runs_status_updated_started",
        "ON ops.workflow_runs(status_id, updated_utc DESC, started_utc DESC)",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_user_workflow_run_migration_stays_index_only():
    text = USER_WORKFLOW_RUN_MIGRATION.read_text().lower()
    forbidden = [
        "create table if not exists ops.mawf_phase",
        "create table if not exists ops.phase",
        "content_text",
        "artifact_content",
        "producer",
        "verifier",
        "critic",
        "execution_history",
        "telemetry",
    ]
    for snippet in forbidden:
        assert snippet not in text


def test_mawf_recoverable_workflow_run_migration_contains_required_index_support():
    text = RECOVERABLE_WORKFLOW_RUN_MIGRATION.read_text()
    required = [
        "020_mawf_recoverable_workflow_runs",
        "019_mawf_workflow_runs_by_user",
        "ix_workflow_runs_recovery_priority",
        "ON ops.workflow_runs(status_id, updated_utc ASC, started_utc ASC)",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_recoverable_workflow_run_migration_stays_index_only():
    text = RECOVERABLE_WORKFLOW_RUN_MIGRATION.read_text().lower()
    forbidden = [
        "create table",
        "workflow_phase",
        "phase_status",
        "content_text",
        "artifact_content",
        "producer",
        "verifier",
        "critic",
        "execution_history",
        "telemetry",
    ]
    for snippet in forbidden:
        assert snippet not in text


def test_mawf_external_task_id_migration_contains_required_schema():
    text = EXTERNAL_TASK_ID_MIGRATION.read_text()
    required = [
        "021_mawf_external_task_id",
        "020_mawf_recoverable_workflow_runs",
        "ALTER TABLE planning.tasks",
        "ADD COLUMN IF NOT EXISTS external_task_id TEXT",
        "ux_tasks_external_task_id",
        "ON planning.tasks(external_task_id)",
        "WHERE external_task_id IS NOT NULL",
    ]
    for snippet in required:
        assert snippet in text


def test_mawf_external_task_id_migration_stays_minimal():
    text = EXTERNAL_TASK_ID_MIGRATION.read_text().lower()
    forbidden = [
        "create table",
        "artifact_content",
        "telemetry",
        "workflow_phase",
        "producer",
        "verifier",
        "critic",
    ]
    for snippet in forbidden:
        assert snippet not in text
