"""Idempotent Obsidian templates, Bases dashboards, and project overview assets."""

from __future__ import annotations

from pathlib import Path

import yaml

from global_memory.vault.paths import safe_component, safe_vault_path

TEMPLATE_TYPES = {
    "Project Overview": ("project", "project", "# Project overview\n\n## Goals\n\n## Current state\n"),
    "Decision": ("decision", "project", "# Decision\n\n## Context\n\n## Choice\n\n## Consequences\n"),
    "Fact": ("fact", "global", "# Fact\n\n## Evidence\n"),
    "Problem and Solution": ("solution", "project", "# Problem\n\n## Verified solution\n\n## Evidence\n"),
    "Preference": ("preference", "global", "# Preference\n\n## Rationale\n"),
    "Convention": ("convention", "global", "# Convention\n\n## Rationale\n\n## Examples\n"),
    "Session Summary": ("session_summary", "session", "# Session summary\n\n## Outcomes\n\n## Explicit references\n"),
    "Entity": ("entity", "global", "# Entity\n\n## Durable facts\n\n## Explicit relationships\n"),
}

BASE_PROPERTIES = """properties:
  file.name:
    displayName: Note
  id:
    displayName: Memory ID
  project:
    displayName: Project
  type:
    displayName: Type
  status:
    displayName: Status
  confidence:
    displayName: Confidence
  updated_at:
    displayName: Updated
"""

DASHBOARDS = {
    "Review Queue.base": BASE_PROPERTIES
    + """formulas:
  unresolved_links: 'visual_links.filter(link(value).asFile() == null)'
views:
  - type: table
    name: AI candidates
    filters:
      and:
        - 'status == "candidate"'
        - 'file.inFolder("00 Inbox/AI Candidates")'
    order: [file.name, id, project, type, confidence, updated_at]
  - type: table
    name: Rejected candidates
    filters:
      and:
        - 'status == "rejected"'
    order: [file.name, id, project, updated_at]
  - type: table
    name: Low confidence
    filters:
      and:
        - 'status == "active"'
        - 'confidence < 0.6'
    order: [file.name, id, project, confidence, updated_at]
  - type: table
    name: Unresolved links
    filters:
      and:
        - 'file.hasProperty("id")'
        - 'formula.unresolved_links.length > 0'
    order: [file.name, id, formula.unresolved_links]
  - type: table
    name: Validation conflicts
    filters:
      and:
        - 'file.ext == "md"'
        - '!file.hasProperty("id")'
        - or:
            - 'file.inFolder("00 Inbox")'
            - 'file.inFolder("10 Global")'
            - 'file.inFolder("15 Organization")'
            - 'file.inFolder("20 Projects")'
            - 'file.inFolder("30 Decisions")'
            - 'file.inFolder("40 Problems and Solutions")'
            - 'file.inFolder("50 Entities")'
            - 'file.inFolder("70 Session Summaries")'
            - 'file.inFolder("90 Archive")'
    order: [file.name, file.path, file.mtime]
""",
    "Knowledge.base": BASE_PROPERTIES
    + """views:
  - type: table
    name: Active decisions
    filters:
      and:
        - 'status == "active"'
        - 'type == "decision"'
    groupBy:
      property: project
      direction: ASC
    order: [file.name, id, project, confidence, updated_at]
  - type: table
    name: Problems and verified solutions
    filters:
      and:
        - 'status == "active"'
        - 'type == "solution"'
    groupBy:
      property: project
      direction: ASC
    order: [file.name, id, project, confidence, updated_at]
  - type: table
    name: Recently updated
    limit: 100
    filters:
      and:
        - 'status == "active"'
    order: [updated_at, file.name, id, project, type]
  - type: table
    name: Project memories
    filters:
      and:
        - 'status == "active"'
        - 'project == this.project'
    order: [type, file.name, id, confidence, updated_at]
""",
    "History.base": BASE_PROPERTIES
    + """views:
  - type: table
    name: Superseded
    filters:
      and:
        - 'status == "superseded"'
    order: [updated_at, file.name, id, project, superseded_by]
  - type: table
    name: Archived
    filters:
      and:
        - 'status == "archived"'
    order: [updated_at, file.name, id, project, type]
""",
}

REVIEW_GUIDE = """# Candidate review

AI-created memories always begin as candidates. Open [[Review Queue.base#AI candidates]], inspect the source and body,
then use `memory_approve` with the candidate ID and its current `updated_at` value. Use `memory_reject` with a reason
when the claim is not durable or verified. Read again before acting if the note changed.

Do not edit lifecycle properties (`id`, `status`, `created_at`, `updated_at`, `supersedes`, or `superseded_by`) by hand.
Normal body and descriptive property edits in Obsidian are indexed by the watcher. Never place credentials in a note.
"""

DASHBOARD_INDEX = """# Global Agent Memory dashboards

## Review

![[Review Queue.base#AI candidates]]

See [[Candidate Review Guide]] before approving or rejecting a candidate.

## Knowledge

![[Knowledge.base#Recently updated]]

## History

![[History.base#Superseded]]
"""


def _template(name: str, memory_type: str, scope: str, body: str) -> str:
    properties: dict[str, object] = {
        "id": "mem_manual-{{date:YYYYMMDDHHmmss}}",
        "title": name,
        "type": memory_type,
        "scope": scope,
    }
    if scope == "project":
        properties["project"] = "Replace with project name"
    properties.update(
        status="candidate",
        confidence=0.5,
        importance=0.5,
        created_at="{{date:YYYY-MM-DD}}T{{time:HH:mm:ss}}Z",
        updated_at="{{date:YYYY-MM-DD}}T{{time:HH:mm:ss}}Z",
        tags=[],
        links=[],
        source_kind="manual",
        source_ref=None,
        supersedes=[],
        superseded_by=None,
    )
    frontmatter = yaml.safe_dump(properties, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{frontmatter}\n---\n{body}"


def install_obsidian_assets(vault: Path) -> list[Path]:
    """Install missing managed visual assets and preserve every existing file."""
    assets: dict[Path, str] = {
        Path("Dashboards/Global Agent Memory.md"): DASHBOARD_INDEX,
        Path("Dashboards/Candidate Review Guide.md"): REVIEW_GUIDE,
    }
    assets.update({Path("Dashboards") / name: content for name, content in DASHBOARDS.items()})
    assets.update(
        {
            Path("Templates") / f"{name}.md": _template(name, memory_type, scope, body)
            for name, (memory_type, scope, body) in TEMPLATE_TYPES.items()
        }
    )
    created: list[Path] = []
    for relative, content in assets.items():
        destination = safe_vault_path(vault, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            continue
        destination.write_text(content)
        created.append(relative)
    return created


def ensure_project_overview(vault: Path, project: str) -> Path:
    """Create a stable project graph hub without overwriting a user's overview."""
    relative = Path("20 Projects") / safe_component(project) / "Project Overview.md"
    destination = safe_vault_path(vault, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        frontmatter = yaml.safe_dump(
            {"global_memory_kind": "project_overview", "project": project}, sort_keys=False, allow_unicode=True
        ).rstrip()
        destination.write_text(
            f"---\n{frontmatter}\n---\n# {project}\n\n![[Dashboards/Knowledge.base#Project memories]]\n"
        )
    return relative
