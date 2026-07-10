"""Priority-ordered project resolution from explicit input and local repository facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from global_memory.projects.git import nearest_git_root, normalize_git_remote, origin_remote
from global_memory.projects.models import ProjectRecord, ProjectRegistry


@dataclass(frozen=True, slots=True)
class ProjectDetection:
    project: ProjectRecord | None
    source: str
    working_directory: Path | None
    git_root: Path | None
    normalized_remote: str | None
    explanation: tuple[str, ...]


class ProjectDetector:
    """Resolve scope without ever inferring a project from query text."""

    def __init__(self, registry: ProjectRegistry) -> None:
        self.registry = registry

    def detect(
        self,
        *,
        working_directory: Path | None = None,
        explicit_project: str | None = None,
    ) -> ProjectDetection:
        resolved_directory = working_directory.expanduser().resolve() if working_directory else None
        git_root = nearest_git_root(resolved_directory) if resolved_directory else None
        if explicit_project is not None:
            project = self.registry.get(explicit_project)
            return ProjectDetection(
                project, "explicit", resolved_directory, git_root, None, ("Explicit project input resolved first.",)
            )
        projects = self.registry.list()
        if resolved_directory is not None:
            root_matches: list[tuple[int, ProjectRecord]] = []
            for project in projects:
                for root in project.roots:
                    resolved_root = root.resolve()
                    if resolved_directory == resolved_root or resolved_directory.is_relative_to(resolved_root):
                        root_matches.append((len(resolved_root.parts), project))
            if root_matches:
                project = max(root_matches, key=lambda item: item[0])[1]
                return ProjectDetection(
                    project,
                    "configured_root",
                    resolved_directory,
                    git_root,
                    None,
                    ("Working directory matched the longest configured project root.",),
                )
        if git_root is not None:
            for project in projects:
                if git_root in {root.resolve() for root in project.roots}:
                    return ProjectDetection(
                        project,
                        "git_root",
                        resolved_directory,
                        git_root,
                        None,
                        ("Nearest Git root matched a configured project root.",),
                    )
            raw_remote = origin_remote(git_root)
            if raw_remote:
                normalized_remote = normalize_git_remote(raw_remote)
                for project in projects:
                    if normalized_remote in project.git_remotes:
                        return ProjectDetection(
                            project,
                            "git_remote",
                            resolved_directory,
                            git_root,
                            normalized_remote,
                            ("Nearest Git origin matched a normalized configured remote.",),
                        )
        if resolved_directory is not None:
            directory_names = [
                resolved_directory.name.casefold(),
                *(parent.name.casefold() for parent in resolved_directory.parents),
            ]
            for directory_name in directory_names:
                for project in projects:
                    names = {project.name.casefold(), *(alias.casefold() for alias in project.aliases)}
                    if directory_name in names:
                        return ProjectDetection(
                            project,
                            "directory_alias",
                            resolved_directory,
                            git_root,
                            None,
                            ("A directory component matched a configured project name or alias.",),
                        )
        return ProjectDetection(
            None,
            "none",
            resolved_directory,
            git_root,
            None,
            ("No explicit, root, Git remote, or directory alias mapping matched.",),
        )
