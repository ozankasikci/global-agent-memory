from __future__ import annotations

from pathlib import Path

import yaml

from global_memory.config import GlobalMemorySettings, PlatformPaths
from global_memory.vault.initialize import initialize
from global_memory.vault.obsidian import DASHBOARDS, TEMPLATE_TYPES


def _paths(tmp_path: Path) -> PlatformPaths:
    return PlatformPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        runtime_dir=tmp_path / "run",
    )


def test_initialization_installs_valid_templates_bases_and_review_workflow(tmp_path: Path) -> None:
    vault = tmp_path / "Global Memory"
    initialize(GlobalMemorySettings(vault_path=vault), _paths(tmp_path))

    templates = sorted((vault / "Templates").glob("*.md"))
    assert len(templates) == len(TEMPLATE_TYPES) == 8
    for template in templates:
        text = template.read_text()
        closing = text.index("\n---\n", 4)
        properties = yaml.safe_load(text[4:closing])
        assert {
            "id",
            "title",
            "type",
            "scope",
            "status",
            "confidence",
            "importance",
            "created_at",
            "updated_at",
            "tags",
            "links",
            "source_kind",
            "supersedes",
            "superseded_by",
        } <= properties.keys()
        assert properties["status"] == "candidate"

    view_names: set[str] = set()
    for name in DASHBOARDS:
        base = yaml.safe_load((vault / "Dashboards" / name).read_text())
        assert "properties" in base and "views" in base
        view_names.update(view["name"] for view in base["views"])
    assert view_names == {
        "AI candidates",
        "Active decisions",
        "Problems and verified solutions",
        "Recently updated",
        "Superseded",
        "Rejected candidates",
        "Archived",
        "Low confidence",
        "Unresolved links",
        "Validation conflicts",
        "Project memories",
    }
    guide = (vault / "Dashboards/Candidate Review Guide.md").read_text()
    assert "memory_approve" in guide and "memory_reject" in guide and "updated_at" in guide


def test_obsidian_assets_never_overwrite_user_edits(tmp_path: Path) -> None:
    vault = tmp_path / "Global Memory"
    existing = vault / "Templates/Decision.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("custom template\n")

    settings = GlobalMemorySettings(vault_path=vault)
    initialize(settings, _paths(tmp_path))
    initialize(settings, _paths(tmp_path))

    assert existing.read_text() == "custom template\n"
