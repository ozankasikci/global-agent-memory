from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from global_memory.projects.git import normalize_git_remote


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:OpenAI/global-memory.git",
        "ssh://git@github.com/OpenAI/global-memory.git",
        "https://github.com/OpenAI/global-memory.git",
        "http://github.com/OpenAI/global-memory/",
    ],
)
def test_ssh_and_https_remote_forms_are_equivalent(remote: str) -> None:
    assert normalize_git_remote(remote) == "github.com/openai/global-memory"


@given(
    host=st.from_regex(r"[a-z]{2,10}\.[a-z]{2,6}", fullmatch=True),
    owner=st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{0,12}", fullmatch=True),
    repo=st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{0,12}", fullmatch=True),
)
def test_scp_and_https_normalize_identically(host: str, owner: str, repo: str) -> None:
    assert normalize_git_remote(f"git@{host}:{owner}/{repo}.git") == normalize_git_remote(
        f"https://{host}/{owner}/{repo}.git"
    )
