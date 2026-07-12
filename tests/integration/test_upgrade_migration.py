from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from global_memory.index.database import MIGRATION_1, MIGRATION_2, MIGRATION_3, IndexDatabase

pytestmark = pytest.mark.integration


def test_upgrade_fixture_preserves_generated_records_and_applies_next_migration(tmp_path: Path) -> None:
    path = tmp_path / "memory.db"
    connection = sqlite3.connect(path)
    connection.executescript(MIGRATION_1 + MIGRATION_2 + MIGRATION_3)
    connection.executemany(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, datetime('now'))",
        [(1,), (2,), (3,)],
    )
    connection.execute("INSERT INTO projects VALUES ('project-1', 'Existing', '[]', '[]', '[]', NULL, 1)")
    connection.commit()
    connection.close()

    upgraded = IndexDatabase(path)

    assert upgraded.connection.execute("SELECT canonical_name FROM projects").fetchone()[0] == "Existing"
    assert upgraded.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 4
    assert upgraded.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='access_grants'"
    ).fetchone()
