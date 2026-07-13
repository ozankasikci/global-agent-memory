from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.integration
def test_installed_module_runs_as_a_subprocess() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "global_memory.cli", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "global-memory 0.1.4"
