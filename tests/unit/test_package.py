from __future__ import annotations

from typer.testing import CliRunner

import global_memory
from global_memory.cli import app


def test_package_exposes_version() -> None:
    assert global_memory.__version__ == "0.1.4"


def test_cli_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "global-memory 0.1.4"
