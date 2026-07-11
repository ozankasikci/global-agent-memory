from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from global_memory.domain.models import MemoryMetadata, MemoryScope, MemoryStatus
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.vault.markdown import parse_note, render_note

NOW = datetime(2026, 7, 11, 9, 0, tzinfo=UTC)


def metadata(**overrides: object) -> MemoryMetadata:
    values: dict[str, object] = {
        "id": "mem_12345678-1234-4234-8234-123456789abc",
        "title": "Unicode decision 🚀",
        "type": "decision",
        "scope": "project",
        "project": "Global Agent Memory",
        "status": "active",
        "confidence": 0.9,
        "importance": 0.8,
        "created_at": NOW,
        "updated_at": NOW,
        "tags": ["mcp", "日本語"],
        "links": ["[[Global Agent Memory]]"],
        "source_kind": "manual",
        "source_ref": None,
        "supersedes": [],
        "superseded_by": None,
        "future_property": {"preserve": True},
    }
    values.update(overrides)
    return MemoryMetadata.model_validate(values)


def test_markdown_round_trip_preserves_body_and_unknown_frontmatter() -> None:
    body = "# Unicode decision 🚀\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint('---')\n```\n"

    parsed = parse_note(render_note(metadata(), body))

    assert parsed.body == body
    assert parsed.metadata.model_extra == {"future_property": {"preserve": True}}
    assert parsed.metadata.tags == ["mcp", "日本語"]


def test_validation_enforces_project_and_temporal_invariants() -> None:
    with pytest.raises(ValueError):
        metadata(project=None)
    with pytest.raises(ValueError):
        metadata(updated_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError):
        metadata(confidence=1.1)
    with pytest.raises(ValueError):
        metadata(superseded_by="mem_other")


def test_unknown_memory_type_is_preserved_for_future_compatibility() -> None:
    note = metadata(type="future_custom_type")
    assert note.type == "future_custom_type"


def test_invalid_frontmatter_has_stable_error() -> None:
    with pytest.raises(GlobalMemoryError) as caught:
        parse_note("# no frontmatter\n")
    assert caught.value.code is ErrorCode.NOTE_INVALID


def test_malicious_yaml_constructor_is_inert_and_rejected() -> None:
    text = "---\nid: !!python/object/apply:os.system ['echo unsafe']\n---\nbody\n"
    with pytest.raises(GlobalMemoryError) as caught:
        parse_note(text)
    assert caught.value.code is ErrorCode.NOTE_INVALID


@given(
    title=st.text(min_size=1, max_size=50).filter(lambda value: "\x00" not in value),
    tag=st.text(min_size=1, max_size=20).filter(lambda value: "\x00" not in value),
)
def test_unicode_metadata_round_trip(title: str, tag: str) -> None:
    original = metadata(title=title, tags=[tag])
    parsed = parse_note(render_note(original, "body\n"))
    assert parsed.metadata.title == title
    assert parsed.metadata.tags == [tag]
    assert parsed.body == "body\n"


def test_scope_and_status_are_closed_lifecycle_values() -> None:
    assert set(MemoryScope) == {"global", "organization", "project", "session", "archive"}
    assert set(MemoryStatus) == {"candidate", "active", "superseded", "archived", "rejected"}
