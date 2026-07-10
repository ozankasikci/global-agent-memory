from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.retrieval.pagination import CursorKey, decode_cursor, encode_cursor
from global_memory.retrieval.ranking import reciprocal_rank_fusion


@given(
    left=st.lists(st.text(min_size=1, max_size=8), unique=True, max_size=20),
    right=st.lists(st.text(min_size=1, max_size=8), unique=True, max_size=20),
)
def test_rrf_is_deterministic_nonnegative_and_rewards_multiple_lists(left: list[str], right: list[str]) -> None:
    first = reciprocal_rank_fusion([left, right])
    second = reciprocal_rank_fusion([left, right])
    assert first == second
    assert all(score >= 0 for score in first.values())
    shared = set(left) & set(right)
    if shared and (set(left) ^ set(right)):
        assert max(first[item] for item in shared) > min(first[item] for item in set(left) ^ set(right))


def test_cursor_round_trip_and_tamper_rejection() -> None:
    key = CursorKey(snapshot="snapshot", score=0.125, updated_at="2026-01-01T00:00:00+00:00", memory_id="mem_a")
    encoded = encode_cursor(key)
    assert decode_cursor(encoded, expected_snapshot="snapshot") == key
    with pytest.raises(GlobalMemoryError) as tampered:
        decode_cursor(encoded[:-2] + "xx", expected_snapshot="snapshot")
    assert tampered.value.code is ErrorCode.NOTE_INVALID
