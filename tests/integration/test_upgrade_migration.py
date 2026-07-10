from __future__ import annotations

from pathlib import Path

import pytest

from global_memory.index.database import IndexDatabase

pytestmark = pytest.mark.integration


def test_upgrade_fixture_preserves_generated_records_and_applies_next_migration(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    database = IndexDatabase(path)
    database.connection.execute("INSERT INTO projects VALUES ('project-1', 'Existing', '[]', '[]', '[]', NULL, 1)")
    database.connection.execute("DROP TABLE index_jobs")
    database.connection.execute("DELETE FROM schema_migrations WHERE version=3")
    database.close()

    upgraded = IndexDatabase(path)

    assert upgraded.connection.execute("SELECT canonical_name FROM projects").fetchone()[0] == "Existing"
    assert upgraded.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 3
    assert upgraded.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='index_jobs'"
    ).fetchone()
