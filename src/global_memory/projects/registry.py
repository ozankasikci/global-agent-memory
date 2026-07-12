"""SQLite adapter for normalized project configuration."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.projects.git import normalize_git_remote
from global_memory.projects.models import ProjectDraft, ProjectRecord


class SQLiteProjectRegistry:
    """Manage stable project identities in rebuildable local configuration state."""

    def __init__(self, database: IndexDatabase) -> None:
        self.database = database

    @staticmethod
    def _from_row(row: Any) -> ProjectRecord:
        return ProjectRecord(
            id=row["id"],
            name=row["canonical_name"],
            aliases=json.loads(row["aliases_json"]),
            roots=[Path(value) for value in json.loads(row["roots_json"])],
            git_remotes=json.loads(row["git_remotes_json"]),
            organization=row["organization"],
            active=bool(row["active"]),
        )

    def list(self, *, include_inactive: bool = False) -> list[ProjectRecord]:
        sql = "SELECT * FROM projects"
        if not include_inactive:
            sql += " WHERE active = 1"
        sql += " ORDER BY canonical_name COLLATE NOCASE, id"
        return [self._from_row(row) for row in self.database.connection.execute(sql).fetchall()]

    def get(self, identifier: str, *, include_inactive: bool = False) -> ProjectRecord:
        normalized = identifier.casefold()
        for project in self.list(include_inactive=include_inactive):
            if project.id == identifier or project.name.casefold() == normalized:
                return project
            if normalized in {alias.casefold() for alias in project.aliases}:
                return project
        raise GlobalMemoryError(
            ErrorCode.PROJECT_NOT_FOUND,
            "No active project matches the requested name, alias, or ID.",
            details={"project": identifier},
            remediation="List configured projects or add the project before using it.",
        )

    def _normalize(self, project_id: str, draft: ProjectDraft, *, active: bool = True) -> ProjectRecord:
        return ProjectRecord(
            id=project_id,
            name=draft.name.strip(),
            aliases=list(dict.fromkeys(alias.strip() for alias in draft.aliases if alias.strip())),
            roots=list(dict.fromkeys(root.expanduser().resolve() for root in draft.roots)),
            git_remotes=list(dict.fromkeys(normalize_git_remote(remote) for remote in draft.git_remotes)),
            organization=draft.organization,
            active=active,
        )

    def _check_names(self, candidate: ProjectRecord) -> None:
        candidate_names = {candidate.name.casefold(), *(alias.casefold() for alias in candidate.aliases)}
        for project in self.list():
            if project.id == candidate.id:
                continue
            existing = {project.name.casefold(), *(alias.casefold() for alias in project.aliases)}
            overlap = candidate_names & existing
            if overlap:
                raise GlobalMemoryError(
                    ErrorCode.NOTE_INVALID,
                    "Project names and aliases must be unambiguous.",
                    details={"conflicts": sorted(overlap), "project_id": project.id},
                )

    def add(self, draft: ProjectDraft, *, project_id: str | None = None) -> ProjectRecord:
        record = self._normalize(project_id or f"proj_{uuid.uuid4()}", draft)
        self._check_names(record)
        with self.database.transaction():
            self.database.connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, 1)",
                (
                    record.id,
                    record.name,
                    json.dumps(record.aliases, ensure_ascii=False),
                    json.dumps([str(root) for root in record.roots]),
                    json.dumps(record.git_remotes),
                    record.organization,
                ),
            )
        return record

    def update(self, identifier: str, patch: dict[str, Any]) -> ProjectRecord:
        current = self.get(identifier)
        if "id" in patch or "active" in patch:
            raise GlobalMemoryError(
                ErrorCode.NOTE_INVALID, "Project identity and lifecycle fields are managed explicitly."
            )
        values = {
            "name": current.name,
            "aliases": current.aliases,
            "roots": current.roots,
            "git_remotes": current.git_remotes,
            "organization": current.organization,
        }
        values.update(patch)
        try:
            draft = ProjectDraft.model_validate(values)
        except ValidationError as exc:
            raise GlobalMemoryError(
                ErrorCode.NOTE_INVALID,
                "The project update is invalid.",
                details={"errors": exc.errors(include_context=False)},
            ) from exc
        record = self._normalize(current.id, draft)
        self._check_names(record)
        with self.database.transaction():
            self.database.connection.execute(
                "UPDATE projects SET canonical_name=?, aliases_json=?, roots_json=?, git_remotes_json=?, "
                "organization=? WHERE id=?",
                (
                    record.name,
                    json.dumps(record.aliases, ensure_ascii=False),
                    json.dumps([str(root) for root in record.roots]),
                    json.dumps(record.git_remotes),
                    record.organization,
                    record.id,
                ),
            )
        return record

    def deactivate(self, identifier: str) -> ProjectRecord:
        current = self.get(identifier)
        with self.database.transaction():
            self.database.connection.execute("UPDATE projects SET active = 0 WHERE id = ?", (current.id,))
        return current.model_copy(update={"active": False})
