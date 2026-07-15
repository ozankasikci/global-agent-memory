from __future__ import annotations

from importlib.metadata import version

from typer.testing import CliRunner

import global_memory
from global_memory.cli import app


def test_package_exposes_version() -> None:
    assert global_memory.__version__ == version("global-memory-mcp")


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == f"global-memory {global_memory.__version__}"
