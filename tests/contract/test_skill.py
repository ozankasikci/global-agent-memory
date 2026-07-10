from __future__ import annotations

import re
from pathlib import Path

import yaml

from global_memory.mcp.contract import load_discovery

SKILL = Path(__file__).parents[2] / "integrations/skills/global-memory/SKILL.md"
REFERENCE = SKILL.parent / "references/contract-v1.md"


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
            "## Keep project isolation",
            "## Propose durable memory",
            "## Update and lifecycle safely",
            "## Completion check",
            "## Failure behavior",
        )
    )
    assert "Skill version: `1.0.0`" in text
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
