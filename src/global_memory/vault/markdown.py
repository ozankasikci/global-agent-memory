"""Loss-conscious YAML frontmatter and Markdown body conversion."""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import ValidationError

from global_memory.domain.models import MemoryMetadata, ParsedMemory
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.security import reject_probable_secrets


class _QuotedStringDumper(yaml.SafeDumper):
    """Quote strings so YAML line-break code points round-trip exactly."""


def _represent_string(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style='"')


_QuotedStringDumper.add_representer(str, _represent_string)


def _invalid(reason: str) -> GlobalMemoryError:
    return GlobalMemoryError(
        ErrorCode.NOTE_INVALID,
        "The Markdown note is not a valid managed memory.",
        details={"reason": reason},
        remediation="Repair the YAML frontmatter while preserving the memory ID and Markdown body.",
    )


def parse_note(text: str) -> ParsedMemory:
    """Parse frontmatter while retaining the body byte-for-byte as text."""
    if not text.startswith("---\n"):
        raise _invalid("missing opening YAML delimiter")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise _invalid("missing closing YAML delimiter")
    raw_yaml = text[4:closing]
    body = text[closing + 5 :]
    try:
        values: Any = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise _invalid(str(exc)) from exc
    if not isinstance(values, dict):
        raise _invalid("frontmatter must be a YAML mapping")
    try:
        metadata = MemoryMetadata.model_validate(values)
    except ValidationError as exc:
        raise _invalid(str(exc)) from exc
    reject_probable_secrets(metadata.title, body, metadata.source_ref, *metadata.tags, *metadata.links)
    return ParsedMemory(metadata=metadata, body=body)


def render_note(metadata: MemoryMetadata, body: str) -> str:
    """Render normalized managed YAML followed by the exact supplied body."""
    values = metadata.model_dump(mode="json")
    frontmatter = yaml.dump(
        values,
        Dumper=_QuotedStringDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).rstrip()
    return f"---\n{frontmatter}\n---\n{body}"
