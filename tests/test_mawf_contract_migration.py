from pathlib import Path


MIGRATION = Path("migrations/versions/016_mawf_contract.py")


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
