"""Project registry entities and ports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectDraft(BaseModel):
    """Validated user input before stable project identity assignment."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    roots: list[Path] = Field(default_factory=list)
    git_remotes: list[str] = Field(default_factory=list)
    organization: str | None = None

    @field_validator("roots")
    @classmethod
    def absolute_roots(cls, values: list[Path]) -> list[Path]:
        if any(not value.expanduser().is_absolute() for value in values):
            raise ValueError("project roots must be absolute")
        return values


class ProjectRecord(BaseModel):
    """Stable normalized project configuration."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    aliases: list[str]
    roots: list[Path]
    git_remotes: list[str]
    organization: str | None
    active: bool = True

    @property
    def normalized_git_remotes(self) -> list[str]:
        return self.git_remotes


class ProjectRegistry(Protocol):
    def list(self, *, include_inactive: bool = False) -> list[ProjectRecord]: ...

    def get(self, identifier: str, *, include_inactive: bool = False) -> ProjectRecord: ...

    def add(self, draft: ProjectDraft, *, project_id: str | None = None) -> ProjectRecord: ...

    def update(self, identifier: str, patch: dict[str, Any]) -> ProjectRecord: ...

    def deactivate(self, identifier: str) -> ProjectRecord: ...
