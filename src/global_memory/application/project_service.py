"""Application operations for project registry management and detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from global_memory.projects.detector import ProjectDetection, ProjectDetector
from global_memory.projects.models import ProjectDraft, ProjectRecord, ProjectRegistry


class ProjectService:
    def __init__(self, registry: ProjectRegistry) -> None:
        self.registry = registry

    def list(self) -> list[ProjectRecord]:
        return self.registry.list()

    def get(self, identifier: str) -> ProjectRecord:
        return self.registry.get(identifier)

    def add(self, draft: ProjectDraft) -> ProjectRecord:
        return self.registry.add(draft)

    def update(self, identifier: str, patch: dict[str, Any]) -> ProjectRecord:
        return self.registry.update(identifier, patch)

    def deactivate(self, identifier: str) -> ProjectRecord:
        return self.registry.deactivate(identifier)

    def detect(self, working_directory: Path | None = None, explicit_project: str | None = None) -> ProjectDetection:
        return ProjectDetector(self.registry).detect(
            working_directory=working_directory, explicit_project=explicit_project
        )
