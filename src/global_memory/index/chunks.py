"""Deterministic Markdown-aware chunking with a replaceable estimator."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass

TokenEstimator = Callable[[str], int]


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    heading_path: str | None
    content: str
    content_hash: str
    estimated_tokens: int


def approximate_tokens(text: str) -> int:
    """Cheap deterministic estimate suitable when no tokenizer is installed."""
    return max(1, (len(text) + 3) // 4)


def _blocks(title: str, body: str) -> list[tuple[str, str | None]]:
    headings: list[str] = [title]
    blocks: list[tuple[str, str | None]] = []
    lines = body.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        line = lines[index]
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            level = len(heading.group(1))
            headings = headings[: max(1, level)]
            while len(headings) < level:
                headings.append("")
            label = heading.group(2)
            if level == 1:
                headings[0] = label
            else:
                headings[level - 1] = label
            index += 1
            continue
        if line.lstrip().startswith("```") or line.lstrip().startswith("~~~"):
            marker = line.lstrip()[:3]
            captured = [line]
            index += 1
            while index < len(lines):
                captured.append(lines[index])
                closing = lines[index].lstrip().startswith(marker)
                index += 1
                if closing:
                    break
            blocks.append(("".join(captured).strip(), " > ".join(part for part in headings if part)))
            continue
        if not line.strip():
            index += 1
            continue
        captured = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^#{1,6}\s+", lines[index]):
            captured.append(lines[index])
            index += 1
        blocks.append(("".join(captured).strip(), " > ".join(part for part in headings if part)))
    return blocks


def chunk_markdown(
    title: str,
    body: str,
    *,
    estimator: TokenEstimator = approximate_tokens,
    target_tokens: int = 550,
    overlap_tokens: int = 50,
    hard_max_tokens: int = 900,
) -> list[Chunk]:
    """Chunk on structural boundaries and keep fenced blocks intact."""
    blocks = _blocks(title, body)
    if not blocks:
        blocks = [(body, title)]
    bounded_blocks: list[tuple[str, str | None]] = []
    for content, heading in blocks:
        if estimator(content) <= hard_max_tokens:
            bounded_blocks.append((content, heading))
            continue
        words = content.split()
        step = max(1, hard_max_tokens - overlap_tokens)
        for start in range(0, len(words), step):
            bounded_blocks.append((" ".join(words[start : start + hard_max_tokens]), heading))
            if start + hard_max_tokens >= len(words):
                break
    grouped: list[tuple[str, str | None]] = []
    current: list[str] = []
    current_heading: str | None = None
    for content, heading in bounded_blocks:
        proposed = "\n\n".join([*current, content])
        if current and estimator(proposed) > target_tokens:
            combined = "\n\n".join(current)
            grouped.append((combined, current_heading))
            overlap = ""
            if (
                overlap_tokens
                and estimator(combined) + overlap_tokens <= hard_max_tokens
                and "```" not in combined
                and "~~~" not in combined
            ):
                overlap = " ".join(combined.split()[-overlap_tokens:])
            current = [part for part in (overlap, content) if part]
        else:
            current.append(content)
        current_heading = heading or current_heading
    if current:
        grouped.append(("\n\n".join(current), current_heading))
    return [
        Chunk(
            ordinal=ordinal,
            heading_path=heading,
            content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            estimated_tokens=estimator(content),
        )
        for ordinal, (content, heading) in enumerate(grouped)
    ]
