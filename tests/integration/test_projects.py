from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from global_memory.application.project_service import ProjectService
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.projects.detector import ProjectDetector
from global_memory.projects.models import ProjectDraft
from global_memory.projects.registry import SQLiteProjectRegistry

pytestmark = pytest.mark.integration


def project_service(tmp_path: Path) -> ProjectService:
    return ProjectService(SQLiteProjectRegistry(IndexDatabase(tmp_path / "data" / "memory.db")))


def test_registry_crud_aliases_and_deactivation(tmp_path: Path) -> None:
    projects = project_service(tmp_path)
    root = tmp_path / "alpha"
    root.mkdir()
    created = projects.add(
        ProjectDraft(
            name="Alpha",
            aliases=["alpha-app"],
            roots=[root],
            git_remotes=["git@github.com:Example/Alpha.git"],
            organization="Example",
        )
    )
    assert projects.get("alpha-app").id == created.id
    assert projects.get("ALPHA").normalized_git_remotes == ["github.com/example/alpha"]

    updated = projects.update(created.id, {"aliases": ["alpha-app", "a-app"], "organization": "New Org"})
    assert updated.organization == "New Org"
    assert projects.get("a-app").organization == "New Org"
    assert [item.id for item in projects.list()] == [created.id]

    with pytest.raises(GlobalMemoryError) as invalid_update:
        projects.update(created.id, {"roots": [Path("relative-root")]})
    assert invalid_update.value.code is ErrorCode.NOTE_INVALID
    assert "ctx" not in invalid_update.value.details["errors"][0]

    projects.deactivate(created.id)
    assert projects.list() == []
    with pytest.raises(GlobalMemoryError) as caught:
        projects.get("Alpha")
    assert caught.value.code is ErrorCode.PROJECT_NOT_FOUND


def test_detection_priority_explicit_then_root_then_remote_then_alias(tmp_path: Path) -> None:
    projects = project_service(tmp_path)
    alpha_root = tmp_path / "alpha"
    nested = alpha_root / "src" / "nested"
    nested.mkdir(parents=True)
    projects.add(ProjectDraft(name="Alpha", aliases=["alpha-alias"], roots=[alpha_root]))
    projects.add(ProjectDraft(name="Explicit", aliases=["explicit"]))

    detector = ProjectDetector(projects.registry)
    explicit = detector.detect(working_directory=nested, explicit_project="Explicit")
    assert explicit.project and explicit.project.name == "Explicit"
    assert explicit.source == "explicit"

    rooted = detector.detect(working_directory=nested)
    assert rooted.project and rooted.project.name == "Alpha"
    assert rooted.source == "configured_root"

    remote_repo = tmp_path / "remote-repo"
    remote_repo.mkdir()
    subprocess.run(["git", "init", "-q", remote_repo], check=True)
    subprocess.run(
        ["git", "-C", remote_repo, "remote", "add", "origin", "git@github.com:Example/Remote.git"], check=True
    )
    projects.add(ProjectDraft(name="Remote", git_remotes=["https://github.com/example/remote.git"]))
    projects.add(ProjectDraft(name="Alias Loses", aliases=["remote-repo"]))
    remote = detector.detect(working_directory=remote_repo)
    assert remote.project and remote.project.name == "Remote"
    assert remote.source == "git_remote"
    assert remote.normalized_remote == "github.com/example/remote"

    alias_dir = tmp_path / "alpha-alias"
    alias_dir.mkdir()
    alias = detector.detect(working_directory=alias_dir)
    assert alias.project and alias.project.name == "Alpha"
    assert alias.source == "directory_alias"


def test_nearest_git_root_mapping_and_unknown_path(tmp_path: Path) -> None:
    projects = project_service(tmp_path)
    repo = tmp_path / "mapped-repo"
    child = repo / "deep" / "child"
    child.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", repo], check=True)
    projects.add(ProjectDraft(name="Mapped", roots=[repo]))
    detector = ProjectDetector(projects.registry)

    detected = detector.detect(working_directory=child)
    assert detected.project and detected.project.name == "Mapped"
    assert detected.source == "configured_root"
    assert detected.git_root == repo.resolve()

    unknown = tmp_path / "unknown"
    unknown.mkdir()
    result = detector.detect(working_directory=unknown)
    assert result.project is None
    assert result.source == "none"


def test_explicit_unknown_project_is_not_inferred_from_query_or_path(tmp_path: Path) -> None:
    projects = project_service(tmp_path)
    path = tmp_path / "somewhere"
    path.mkdir()
    with pytest.raises(GlobalMemoryError) as caught:
        ProjectDetector(projects.registry).detect(working_directory=path, explicit_project="Missing")
    assert caught.value.code is ErrorCode.PROJECT_NOT_FOUND
