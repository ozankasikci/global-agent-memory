"""Load the generated MCP V1 contract and build common envelopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from global_memory.errors import GlobalMemoryError

CONTRACT_VERSION = 1


def contract_root() -> Path:
    repository = Path(__file__).resolve().parents[3] / "contracts" / "mcp" / "v1"
    if repository.is_dir():
        return repository
    return Path(__file__).resolve().parents[1] / "_contract" / "mcp" / "v1"


def load_discovery() -> dict[str, Any]:
    value = json.loads((contract_root() / "discovery.json").read_text())
    if not isinstance(value, dict):
        raise RuntimeError("The generated MCP discovery contract must be a JSON object.")
    return value


def success(
    data: Any, *, warnings: list[str] | tuple[str, ...] = (), diagnostics: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "ok": True,
        "data": data,
        "warnings": list(warnings),
        "diagnostics": diagnostics,
    }


def failure(error: GlobalMemoryError) -> dict[str, Any]:
    return {"contract_version": CONTRACT_VERSION, "ok": False, "error": error.as_dict()}
