"""Validated memory entities and value types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

SUPPORTED_MEMORY_TYPES = (
    "project",
    "decision",
    "fact",
    "solution",
    "preference",
    "convention",
    "session_summary",
    "entity",
    "reference",
)


class MemoryScope(StrEnum):
    """Applicability boundary for a memory."""

    GLOBAL = "global"
    ORGANIZATION = "organization"
    PROJECT = "project"
    SESSION = "session"
    ARCHIVE = "archive"


class MemoryStatus(StrEnum):
    """Auditable lifecycle state for a memory."""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class MemoryVisibility(StrEnum):
    """Who may discover or read a memory through agent-facing surfaces."""

    STANDARD = "standard"
    PROTECTED = "protected"
    SEALED = "sealed"


class MemoryPermission(StrEnum):
    """Maximum operation allowed by a temporary access grant."""

    READ = "read"
    EDIT = "edit"
    MANAGE = "manage"


class MemoryMetadata(BaseModel):
    """Managed YAML properties while preserving unknown future properties."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(pattern=r"^mem_[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1)
    type: str = Field(min_length=1)
    scope: MemoryScope
    project: str | None = None
    status: MemoryStatus
    visibility: MemoryVisibility = MemoryVisibility.STANDARD
    access_policy: str = "user_approval"
    allowed_projects: list[str] = Field(default_factory=list)
    max_permission: MemoryPermission = Field(
        default=MemoryPermission.READ,
        validation_alias=AliasChoices("max_permission", "default_permission"),
    )
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source_kind: str = "manual"
    source_ref: str | None = None
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_invariants(self) -> MemoryMetadata:
        if self.scope is MemoryScope.PROJECT and not self.project:
            raise ValueError("project-scoped memories require a project")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")
        if self.status is MemoryStatus.ACTIVE and self.superseded_by is not None:
            raise ValueError("active memory cannot have superseded_by")
        if self.access_policy not in {"user_approval", "per_access"}:
            raise ValueError("access_policy must be user_approval or per_access")
        return self


class MemoryDraft(BaseModel):
    """User or agent supplied fields before identity and lifecycle assignment."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    type: str
    scope: MemoryScope
    project: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    source_kind: str = "ai"
    source_ref: str | None = None

    @field_validator("type")
    @classmethod
    def require_supported_type(cls, value: str) -> str:
        if value not in SUPPORTED_MEMORY_TYPES:
            raise ValueError(f"unsupported memory type: {value}")
        return value

    @model_validator(mode="after")
    def validate_project(self) -> MemoryDraft:
        if self.scope is MemoryScope.PROJECT and not self.project:
            raise ValueError("project-scoped memories require a project")
        return self


class ParsedMemory(BaseModel):
    """A validated frontmatter entity paired with exact Markdown body text."""

    metadata: MemoryMetadata
    body: str


@dataclass(frozen=True, slots=True)
class StoredMemory:
    """A managed memory and its current storage location."""

    metadata: MemoryMetadata
    body: str
    path: Path
    vault_path: Path

    @property
    def relative_path(self) -> Path:
        return self.path.relative_to(self.vault_path)

    @property
    def version(self) -> str:
        return self.metadata.updated_at.isoformat()


@dataclass(frozen=True, slots=True)
class SupersedeResult:
    """The reciprocal result of one explicit supersession operation."""

    old: StoredMemory
    replacement: StoredMemory


@dataclass(frozen=True, slots=True)
class HardDeleteResult:
    """Safe receipt for an explicit destructive deletion."""

    memory_id: str
    relative_path: Path
    hard_deleted: bool = True


def metadata_with_patch(metadata: MemoryMetadata, patch: dict[str, Any], *, updated_at: datetime) -> MemoryMetadata:
    """Apply an explicit metadata patch through full invariant validation."""
    values = metadata.model_dump()
    values.update(patch)
    values["updated_at"] = updated_at
    return MemoryMetadata.model_validate(values)
