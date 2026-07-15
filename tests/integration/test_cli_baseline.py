from __future__ import annotations

import subprocess
import sys

import pytest

import global_memory


@pytest.mark.integration
def test_installed_module_runs_as_a_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "global_memory.cli", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == f"global-memory {global_memory.__version__}"
