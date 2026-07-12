from __future__ import annotations

from global_memory.index.chunks import chunk_markdown


def words(text: str) -> int:
    return len(text.split())


def test_small_note_is_one_deterministic_chunk_with_heading_context() -> None:
    body = "# Title\n\n## Decision\n\nUse SQLite FTS5.\n"
    first = chunk_markdown("Title", body, estimator=words, target_tokens=50, overlap_tokens=5)
    second = chunk_markdown("Title", body, estimator=words, target_tokens=50, overlap_tokens=5)
    assert first == second
    assert len(first) == 1
    assert first[0].ordinal == 0
    assert first[0].heading_path == "Title > Decision"


def test_chunking_prefers_boundaries_and_does_not_split_fenced_code() -> None:
    body = (
        "# Indexing\n\n"
        + "First paragraph with several searchable words.\n\n" * 4
        + "```python\n"
        + "print('do not split this block')\n" * 15
        + "```\n\n"
        + "## Recovery\n\n"
        + "Final paragraph with recovery details.\n" * 4
    )
    chunks = chunk_markdown("Index", body, estimator=words, target_tokens=30, overlap_tokens=5)
    code_chunks = [chunk for chunk in chunks if "```python" in chunk.content]
    assert len(code_chunks) == 1
    assert code_chunks[0].content.count("```") == 2
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.content_hash for chunk in chunks)


def test_oversized_structural_block_uses_hard_ceiling() -> None:
    body = "# Huge\n\n" + "word " * 120
    chunks = chunk_markdown("Huge", body, estimator=words, target_tokens=20, overlap_tokens=5, hard_max_tokens=40)
    assert len(chunks) > 1
    assert all(chunk.estimated_tokens <= 40 for chunk in chunks)
