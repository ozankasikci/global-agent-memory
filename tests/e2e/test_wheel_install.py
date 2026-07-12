from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_fresh_wheel_contains_contract_and_console_entry_points(tmp_path: Path) -> None:
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(tmp_path / "dist")], check=True)
    wheel = next((tmp_path / "dist").glob("*.whl"))
    environment = tmp_path / "venv"
    subprocess.run(["uv", "venv", "--python", "3.12", str(environment)], check=True)
    python = environment / "bin/python"
    subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True)
    completed = subprocess.run(
        [
            str(python),
            "-c",
            "from global_memory.mcp.contract import load_discovery; "
            "assert len(load_discovery()['tools']) == 17; "
            "from pathlib import Path; import global_memory; "
            "assert (Path(global_memory.__file__).parent / '_dashboard/index.html').is_file(); "
            "from global_memory.integrations.manager import integration_root; "
            "assert (integration_root() / 'skills/global-memory/SKILL.md').is_file(); "
            "assert (integration_root() / 'skills/gam-context/SKILL.md').is_file(); "
            "assert (integration_root() / 'skills/gam-dashboard/SKILL.md').is_file(); "
            "import global_memory.cli",
        ],
        check=True,
    )
    assert completed.returncode == 0
    assert subprocess.run([str(environment / "bin/global-memory"), "--version"], check=True).returncode == 0
    assert subprocess.run([str(environment / "bin/global-memoryd"), "--help"], check=True).returncode == 0
    assert subprocess.run([str(environment / "bin/global-memory-mcp"), "--help"], check=True).returncode == 0
