from __future__ import annotations

import importlib.util
from pathlib import Path


class FakeOp:
    def __init__(self):
        self.sql = []

    def execute(self, value):
        self.sql.append(" ".join(value.split()))


def load_migration():
    path = Path(__file__).parents[1] / "migrations/versions/029_work_memory_trust.py"
    spec = importlib.util.spec_from_file_location("migration_029", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_migration_029_upgrade_and_dependency_safe_downgrade():
    module = load_migration(); fake = FakeOp(); module.op = fake
    module.upgrade()
    upgrade = "\n".join(fake.sql)
    assert "ADD COLUMN content_kind" in upgrade
    assert "CREATE TABLE memory.learned_import_reports" in upgrade
    assert "CREATE TABLE memory.learned_import_unresolved" in upgrade
    assert "WHERE memory_type = 'operator_note'" in upgrade
    fake.sql.clear(); module.downgrade(); downgrade = fake.sql
    assert downgrade.index("DROP TABLE memory.learned_import_unresolved") < downgrade.index("DROP TABLE memory.learned_import_reports")
    assert downgrade.index("DROP INDEX memory.idx_learned_records_operator_note_review") < downgrade.index("ALTER TABLE memory.learned_records DROP COLUMN content_kind")
    assert not any("evidence_entity_id" in sql or "evidence_chunk_id" in sql for sql in downgrade)
