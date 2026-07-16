"""Project-safe keyword, semantic, hybrid, and metadata retrieval."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from global_memory.access import AccessService
from global_memory.embeddings.base import EmbeddingProvider
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.index.indexer import Indexer
from global_memory.index.vectors import VectorStore
from global_memory.projects.detector import ProjectDetector
from global_memory.retrieval.pagination import CursorKey, decode_cursor, encode_cursor
from global_memory.retrieval.ranking import reciprocal_rank_fusion


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    project: str | None = None
    working_directory: Path | None = None
    scopes: list[str] | None = None
    types: list[str] | None = None
    tags: list[str] | None = None
    statuses: list[str] | None = None
    cross_project: bool = False
    include_candidates: bool = False
    include_archived: bool = False
    include_rejected: bool = False
    include_superseded: bool = False
    mode: Literal["hybrid", "keyword", "semantic", "metadata"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=100)
    cursor: str | None = None
    access_grant: str | None = None


@dataclass(frozen=True, slots=True)
class SupportingPassage:
    excerpt: str
    heading: str | None
    keyword_rank: int | None
    semantic_rank: int | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    memory_id: str
    title: str
    path: str
    type: str
    scope: str
    project: str | None
    status: str
    excerpt: str
    heading: str | None
    score: float
    keyword_rank: int | None
    semantic_rank: int | None
    reasons: tuple[str, ...]
    updated_at: str
    obsidian_uri: str
    supporting_passages: tuple[SupportingPassage, ...]
    labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchPage:
    results: tuple[SearchResult, ...]
    next_cursor: str | None
    warnings: tuple[str, ...]
    mode_used: str
    index_snapshot: str
    project: str | None
    project_source: str
    project_explanation: tuple[str, ...]


@dataclass(slots=True)
class _Candidate:
    chunk_id: str
    memory_id: str
    title: str
    path: str
    type: str
    scope: str
    project: str | None
    status: str
    content: str
    heading: str | None
    importance: float
    updated_at: str
    tags: tuple[str, ...]
    visibility: str
    allowed_projects: tuple[str, ...]
    keyword_rank: int | None = None
    semantic_rank: int | None = None
    reasons: list[str] = field(default_factory=list)


class SearchService:
    def __init__(
        self,
        database: IndexDatabase,
        keyword: Indexer,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        vectors: VectorStore | None = None,
        project_detector: ProjectDetector | None = None,
        access: AccessService | None = None,
        vault_name: str = "Global Agent Memory",
        keyword_candidates: int = 50,
        semantic_candidates: int = 50,
        rrf_k: int = 60,
    ) -> None:
        self.database = database
        self.keyword = keyword
        self.embedding_provider = embedding_provider
        self.vectors = vectors
        self.project_detector = project_detector
        self.access = access
        self.vault_name = vault_name
        self.keyword_candidates = keyword_candidates
        self.semantic_candidates = semantic_candidates
        self.rrf_k = rrf_k

    def _snapshot(self) -> str:
        rows = self.database.connection.execute(
            "SELECT id, content_hash, indexed_at, deleted_at FROM documents ORDER BY id"
        ).fetchall()
        state = "\n".join(
            f"{row['id']}:{row['content_hash']}:{row['indexed_at']}:{row['deleted_at'] or ''}" for row in rows
        )
        # Recency scoring advances at UTC-day boundaries. Include that clock
        # boundary so a pagination cursor cannot silently span two score sets.
        state = f"{state}\nscore-date:{datetime.now(UTC).date().isoformat()}"
        return hashlib.sha256(state.encode()).hexdigest()[:20]

    def _resolve_project(self, request: SearchRequest) -> tuple[str | None, str, tuple[str, ...]]:
        if self.project_detector is not None:
            detection = self.project_detector.detect(
                working_directory=request.working_directory, explicit_project=request.project
            )
            return (
                detection.project.name if detection.project else None,
                detection.source,
                detection.explanation,
            )
        source = "explicit" if request.project else "none"
        explanation = ("Explicit project input was used.",) if request.project else ("No project was resolved.",)
        return request.project, source, explanation

    def _fetch_chunk(self, chunk_id: str) -> _Candidate | None:
        row = self.database.connection.execute(
            """
            SELECT c.id AS chunk_id, c.content, c.heading_path, d.*
            FROM chunks c JOIN documents d ON d.id=c.document_id
            WHERE c.id=? AND d.deleted_at IS NULL
            """,
            (chunk_id,),
        ).fetchone()
        if row is None:
            return None
        metadata = json.loads(row["metadata_json"])
        return _Candidate(
            chunk_id=row["chunk_id"],
            memory_id=row["id"],
            title=row["title"],
            path=row["path"],
            type=row["type"],
            scope=row["scope"],
            project=row["project"],
            status=row["status"],
            content=row["content"],
            heading=row["heading_path"],
            importance=float(row["importance"]),
            updated_at=row["updated_at"],
            tags=tuple(metadata.get("tags", [])),
            visibility=row["visibility"],
            allowed_projects=tuple(metadata.get("allowed_projects", [])),
        )

    @staticmethod
    def _status_set(request: SearchRequest) -> set[str]:
        statuses = set(request.statuses or ["active"])
        if request.include_candidates:
            statuses.add("candidate")
        if request.include_archived:
            statuses.add("archived")
        if request.include_rejected:
            statuses.add("rejected")
        if request.include_superseded:
            statuses.add("superseded")
        return statuses

    def _allowed(
        self,
        candidate: _Candidate,
        request: SearchRequest,
        project: str | None,
        protected_ids: set[str],
    ) -> bool:
        if candidate.visibility == "sealed":
            return False
        if (
            candidate.visibility == "protected"
            and candidate.allowed_projects
            and project not in candidate.allowed_projects
        ):
            return False
        if candidate.visibility == "protected" and candidate.memory_id not in protected_ids:
            return False
        if candidate.status not in self._status_set(request):
            return False
        if request.scopes and candidate.scope not in request.scopes:
            return False
        if request.types and candidate.type not in request.types:
            return False
        if request.tags and not set(request.tags) <= set(candidate.tags):
            return False
        if candidate.scope in {"global", "organization"}:
            return True
        if candidate.scope == "archive" and request.include_archived:
            return True
        if project is None:
            return False
        return candidate.project == project or request.cross_project

    def _metadata_candidates(self, query: str) -> list[_Candidate]:
        needle = query.casefold()
        rows = self.database.connection.execute(
            """
            SELECT c.id FROM documents d JOIN chunks c ON c.document_id=d.id AND c.ordinal=0
            WHERE d.deleted_at IS NULL AND d.visibility != 'sealed' ORDER BY d.updated_at DESC, d.id
            """
        ).fetchall()
        candidates = [candidate for row in rows if (candidate := self._fetch_chunk(row["id"])) is not None]
        return [
            candidate
            for candidate in candidates
            if needle in candidate.memory_id.casefold()
            or needle in candidate.title.casefold()
            or any(needle in tag.casefold() for tag in candidate.tags)
        ]

    def _collect(
        self,
        request: SearchRequest,
        project: str | None,
        *,
        semantic_vector: list[float] | None = None,
        semantic_error: GlobalMemoryError | None = None,
    ) -> tuple[dict[str, _Candidate], list[str], list[str], list[str], str]:
        candidates: dict[str, _Candidate] = {}
        keyword_order: list[str] = []
        semantic_order: list[str] = []
        warnings: list[str] = []
        mode_used = request.mode
        protected_ids: set[str] = set()
        if request.access_grant:
            if self.access is None:
                raise GlobalMemoryError(ErrorCode.ACCESS_GRANT_INVALID, "Access grants are unavailable.")
            protected_ids = self.access.scope_for(
                request.access_grant,
                permission="read",
                project=project,
                consume=True,
            )
        protected_match = False
        if request.mode in {"keyword", "hybrid"}:
            for result in self.keyword.keyword_search(
                request.query,
                scopes=request.scopes,
                types=request.types,
                statuses=sorted(self._status_set(request)),
                tags=request.tags,
                applicable_project=project,
                cross_project=request.cross_project,
                include_archive_scope=request.include_archived,
                apply_default_scope=True,
                limit=self.keyword_candidates,
            ):
                candidate = self._fetch_chunk(result.chunk_id)
                if (
                    candidate is not None
                    and candidate.visibility == "protected"
                    and (not candidate.allowed_projects or project in candidate.allowed_projects)
                    and candidate.memory_id not in protected_ids
                ):
                    protected_match = True
                if candidate is None or not self._allowed(candidate, request, project, protected_ids):
                    continue
                candidate.keyword_rank = len(keyword_order) + 1
                candidate.reasons.append(f"keyword_rank:{candidate.keyword_rank}")
                candidates[candidate.chunk_id] = candidate
                keyword_order.append(candidate.chunk_id)
        if request.mode == "metadata":
            for candidate in self._metadata_candidates(request.query):
                if (
                    candidate.visibility == "protected"
                    and (not candidate.allowed_projects or project in candidate.allowed_projects)
                    and candidate.memory_id not in protected_ids
                ):
                    protected_match = True
                if self._allowed(candidate, request, project, protected_ids):
                    candidate.reasons.append("metadata_match")
                    candidates[candidate.chunk_id] = candidate
            if protected_match:
                warnings.append("protected_memory_may_be_relevant")
            return candidates, [], [], warnings, mode_used
        if request.mode in {"semantic", "hybrid"}:
            try:
                if semantic_error is not None:
                    raise semantic_error
                if self.embedding_provider is None:
                    raise GlobalMemoryError(
                        ErrorCode.EMBEDDING_PROVIDER_UNAVAILABLE, "No embedding provider is configured."
                    )
                if self.vectors is None or not self.vectors.available:
                    raise GlobalMemoryError(ErrorCode.VECTOR_INDEX_UNAVAILABLE, "No vector index is available.")
                vector = (
                    semantic_vector
                    if semantic_vector is not None
                    else self.embedding_provider.embed([request.query])[0]
                )
                for match in self.vectors.search(
                    self.embedding_provider.provider,
                    self.embedding_provider.model,
                    vector,
                    limit=self.semantic_candidates,
                ):
                    candidate = candidates.get(match.chunk_id) or self._fetch_chunk(match.chunk_id)
                    if (
                        candidate is not None
                        and candidate.visibility == "protected"
                        and (not candidate.allowed_projects or project in candidate.allowed_projects)
                        and candidate.memory_id not in protected_ids
                    ):
                        protected_match = True
                    if candidate is None or not self._allowed(candidate, request, project, protected_ids):
                        continue
                    candidate.semantic_rank = len(semantic_order) + 1
                    candidate.reasons.append(f"semantic_rank:{candidate.semantic_rank}")
                    candidates[candidate.chunk_id] = candidate
                    semantic_order.append(candidate.chunk_id)
            except GlobalMemoryError:
                if request.mode == "semantic":
                    raise
                warnings.append("semantic_unavailable_keyword_fallback")
                mode_used = "keyword"
        if protected_match:
            warnings.append("protected_memory_may_be_relevant")
        return candidates, keyword_order, semantic_order, warnings, mode_used

    def _adjust(self, candidate: _Candidate, project: str | None) -> tuple[float, list[str], list[str]]:
        adjustment = 0.0
        reasons: list[str] = []
        labels: list[str] = []
        if candidate.project == project and project is not None:
            adjustment += 0.02
            reasons.append("exact_project_match")
        elif candidate.scope in {"global", "organization"}:
            adjustment += 0.01
            reasons.append(f"{candidate.scope}_applicability")
        elif project is not None and candidate.project != project:
            labels.append("cross_project")
            adjustment -= 0.005
        adjustment += min(max(candidate.importance, 0.0), 1.0) * 0.01
        reasons.append("importance_adjustment")
        if candidate.type == "session_summary":
            adjustment -= 0.01
            reasons.append("session_summary_penalty")
        try:
            age_days = max(0, (datetime.now(UTC).date() - datetime.fromisoformat(candidate.updated_at).date()).days)
            recency = max(0.0, 1.0 - min(age_days, 365.0) / 365.0) * 0.005
            adjustment += recency
            reasons.append("recency_adjustment")
        except ValueError:
            pass
        if candidate.status != "active":
            adjustment -= 0.02
            labels.append(candidate.status)
            reasons.append("non_active_status")
        else:
            adjustment += 0.005
            reasons.append("active_status_adjustment")
        if candidate.visibility == "protected":
            labels.append("protected")
        return adjustment, reasons, labels

    def _results(
        self,
        candidates: dict[str, _Candidate],
        keyword_order: list[str],
        semantic_order: list[str],
        project: str | None,
    ) -> list[SearchResult]:
        rankings = [ranking for ranking in (keyword_order, semantic_order) if ranking]
        fused = reciprocal_rank_fusion(rankings, k=self.rrf_k) if rankings else {key: 1.0 for key in candidates}
        grouped: dict[str, list[tuple[float, _Candidate, list[str], list[str]]]] = {}
        for chunk_id, candidate in candidates.items():
            adjustment, reasons, labels = self._adjust(candidate, project)
            grouped.setdefault(candidate.memory_id, []).append(
                (fused.get(chunk_id, 0.0) + adjustment, candidate, reasons, labels)
            )
        results: list[SearchResult] = []
        for passages in grouped.values():
            passages.sort(key=lambda item: (-item[0], item[1].chunk_id))
            score, primary, adjusted_reasons, labels = passages[0]
            all_candidates = [item[1] for item in passages]
            keyword_rank = min(
                (item.keyword_rank for item in all_candidates if item.keyword_rank is not None), default=None
            )
            semantic_rank = min(
                (item.semantic_rank for item in all_candidates if item.semantic_rank is not None), default=None
            )
            result_reasons = tuple(dict.fromkeys([*primary.reasons, *adjusted_reasons]))
            supporting = tuple(
                SupportingPassage(item.content[:500], item.heading, item.keyword_rank, item.semantic_rank)
                for _, item, _, _ in passages[1:3]
            )
            uri = f"obsidian://open?vault={quote(self.vault_name, safe='')}&file={quote(primary.path, safe='')}"
            results.append(
                SearchResult(
                    memory_id=primary.memory_id,
                    title=primary.title,
                    path=primary.path,
                    type=primary.type,
                    scope=primary.scope,
                    project=primary.project,
                    status=primary.status,
                    excerpt=primary.content[:500],
                    heading=primary.heading,
                    score=score,
                    keyword_rank=keyword_rank,
                    semantic_rank=semantic_rank,
                    reasons=result_reasons,
                    updated_at=primary.updated_at,
                    obsidian_uri=uri,
                    supporting_passages=supporting,
                    labels=tuple(dict.fromkeys(labels)),
                )
            )
        results.sort(key=lambda result: result.memory_id)
        results.sort(key=lambda result: result.updated_at, reverse=True)
        results.sort(key=lambda result: result.score, reverse=True)
        return results

    def _search(
        self,
        request: SearchRequest,
        *,
        semantic_vector: list[float] | None = None,
        semantic_error: GlobalMemoryError | None = None,
    ) -> SearchPage:
        project, project_source, project_explanation = self._resolve_project(request)
        snapshot = self._snapshot()
        fingerprint_data = request.model_dump(mode="json", exclude={"cursor", "limit"})
        fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()[:12]
        cursor_snapshot = f"{snapshot}:{fingerprint}"
        candidates, keyword_order, semantic_order, warnings, mode_used = self._collect(
            request,
            project,
            semantic_vector=semantic_vector,
            semantic_error=semantic_error,
        )
        results = self._results(candidates, keyword_order, semantic_order, project)
        if request.cursor:
            key = decode_cursor(request.cursor, expected_snapshot=cursor_snapshot)
            results = [
                result
                for result in results
                if result.score < key.score
                or (result.score == key.score and result.updated_at < key.updated_at)
                or (
                    result.score == key.score
                    and result.updated_at == key.updated_at
                    and result.memory_id > key.memory_id
                )
            ]
        page_results = results[: request.limit]
        next_cursor = None
        if len(results) > request.limit and page_results:
            last = page_results[-1]
            next_cursor = encode_cursor(CursorKey(cursor_snapshot, last.score, last.updated_at, last.memory_id))
        return SearchPage(
            results=tuple(page_results),
            next_cursor=next_cursor,
            warnings=tuple(warnings),
            mode_used=mode_used,
            index_snapshot=snapshot,
            project=project,
            project_source=project_source,
            project_explanation=project_explanation,
        )

    def search(self, request: SearchRequest) -> SearchPage:
        """Search synchronously for direct and offline callers."""
        return self._search(request)

    async def search_async(self, request: SearchRequest) -> SearchPage:
        """Search without blocking the daemon event loop on embedding I/O."""
        if (
            request.mode not in {"hybrid", "semantic"}
            or self.embedding_provider is None
            or self.vectors is None
            or not self.vectors.available
        ):
            return self._search(request)
        try:
            vector = (await asyncio.to_thread(self.embedding_provider.embed, [request.query]))[0]
        except GlobalMemoryError as exc:
            return self._search(request, semantic_error=exc)
        return self._search(request, semantic_vector=vector)
