from __future__ import annotations

import re
from pathlib import Path

import yaml

from global_memory.mcp.contract import load_discovery

SKILL = Path(__file__).parents[2] / "integrations/skills/global-memory/SKILL.md"
REFERENCE = SKILL.parent / "references/contract-v1.md"
COMMANDS = {path.parent.name: path for path in (SKILL.parent.parent).glob("gam-*/SKILL.md")}


def test_skill_frontmatter_versions_and_required_workflow_sections() -> None:
    text = SKILL.read_text()
    closing = text.index("\n---\n", 4)
    frontmatter = yaml.safe_load(text[4:closing])
    assert set(frontmatter) == {"name", "description"}
    assert frontmatter["name"] == "global-memory"
    assert all(
        heading in text
        for heading in (
            "## Before substantial work",
            "## Open the dashboard",
            "## Keep project isolation",
            "## Propose durable memory",
            "## Update and lifecycle safely",
            "## Completion check",
            "## Failure behavior",
        )
    )
    assert "Skill version: `1.1.0`" in text
    assert "MCP contract version: `v1`" in text


def test_skill_is_client_neutral_secure_and_names_only_frozen_tools() -> None:
    text = SKILL.read_text() + "\n" + REFERENCE.read_text()
    frozen = {tool["name"] for tool in load_discovery()["tools"]}
    mentioned = set(re.findall(r"`(memory_[a-z_]+)`", text))
    assert mentioned <= frozen
    assert {"memory_context", "memory_search", "memory_get", "memory_remember", "memory_update"} <= mentioned
    assert "credentials" in text and "transient logs" in text and "cross_project=false" in text
    assert "Claude" not in text and "Codex" not in text
    assert "expected_updated_at" in text and "VERSION_CONFLICT" in text


def test_basic_command_skills_are_valid_and_use_only_frozen_capabilities() -> None:
    assert set(COMMANDS) == {"gam-context", "gam-search", "gam-remember", "gam-review", "gam-dashboard"}
    frozen = {tool["name"] for tool in load_discovery()["tools"]}
    for name, path in COMMANDS.items():
        text = path.read_text()
        closing = text.index("\n---\n", 4)
        frontmatter = yaml.safe_load(text[4:closing])
        assert frontmatter["name"] == name
        assert frontmatter["description"]
        mentioned = set(re.findall(r"`(memory_[a-z_]+)`", text))
        assert mentioned <= frozen
    assert "memory_context" in COMMANDS["gam-context"].read_text()
    assert "memory_search" in COMMANDS["gam-search"].read_text()
    assert "memory_remember" in COMMANDS["gam-remember"].read_text()
    assert "memory://v1/candidates" in COMMANDS["gam-review"].read_text()
    assert "memory_dashboard_open" in COMMANDS["gam-dashboard"].read_text()
