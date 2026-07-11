"""Complete low-level MCP V1 adapter backed by application services."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import jsonschema
from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from pydantic import AnyUrl, BaseModel, ValidationError

from global_memory import __version__
from global_memory.application.memory_service import MemoryService
from global_memory.application.project_service import ProjectService
from global_memory.domain.models import HardDeleteResult, MemoryDraft, StoredMemory, SupersedeResult
from global_memory.domain.protocols import MutationRecord
from global_memory.embeddings.base import EmbeddingProvider
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase, open_recoverable_database
from global_memory.index.embedding_indexer import EmbeddingIndexer
from global_memory.index.indexer import Indexer
from global_memory.index.jobs import IndexJobQueue
from global_memory.index.mutations import SQLiteMutationStore
from global_memory.index.vectors import SqliteVecStore
from global_memory.projects.detector import ProjectDetector
from global_memory.projects.models import ProjectDraft
from global_memory.projects.registry import SQLiteProjectRegistry
from global_memory.retrieval.context import ContextPacker
from global_memory.retrieval.search import SearchRequest, SearchService
from global_memory.vault.paths import safe_vault_path
from global_memory.vault.repository import VaultRepository

from .contract import CONTRACT_VERSION, failure, load_discovery, success


def _jsonable(value: Any) -> Any:
    if isinstance(value, StoredMemory):
        return {
            "metadata": value.metadata.model_dump(mode="json"),
            "body": value.body,
            "path": str(value.path),
            "relative_path": value.relative_path.as_posix(),
            "version": value.version,
        }
    if isinstance(value, SupersedeResult):
        return {"old": _jsonable(value.old), "replacement": _jsonable(value.replacement)}
    if isinstance(value, HardDeleteResult):
        return {
            "memory_id": value.memory_id,
            "relative_path": value.relative_path.as_posix(),
            "hard_deleted": value.hard_deleted,
        }
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (Path, date, datetime)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


class _MutationGuard:
    def __init__(self, store: SQLiteMutationStore) -> None:
        self.store = store

    def execute(self, request_id: str, operation: str, payload: dict[str, Any], action: Any) -> dict[str, Any]:
        encoded = json.dumps(_jsonable(payload), sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(encoded.encode()).hexdigest()
        existing = self.store.get(request_id)
        if existing:
            if existing.operation != operation or existing.payload_hash != payload_hash:
                raise GlobalMemoryError(
                    ErrorCode.REQUEST_ID_CONFLICT,
                    "The request ID was already used with a different mutation payload.",
                    details={"request_id": request_id, "original_operation": existing.operation},
                    remediation="Generate a new request ID for a different mutation.",
                )
            return existing.result
        result = _jsonable(action())
        if not isinstance(result, dict):
            raise RuntimeError("Guarded adapter mutations must return an object result.")
        self.store.save(request_id, MutationRecord(operation=operation, payload_hash=payload_hash, result=result))
        return result


@dataclass(slots=True)
class ServiceContainer:
    vault_path: Path
    state_path: Path
    database: IndexDatabase
    repository: VaultRepository
    indexer: Indexer
    memory: MemoryService
    projects: ProjectService
    search: SearchService
    context: ContextPacker
    mutations: SQLiteMutationStore
    vectors: SqliteVecStore
    embedding_indexer: EmbeddingIndexer
    embedding_provider: EmbeddingProvider | None
    index_jobs: IndexJobQueue
    transport: str
    vault_name: str
    watcher_state: str = "not_started"
    dashboard_launcher: Callable[[bool], dict[str, Any]] | None = None

    @property
    def guard(self) -> _MutationGuard:
        return _MutationGuard(self.mutations)


def build_container(
    vault_path: Path,
    state_path: Path,
    *,
    transport: str = "direct",
    embedding_provider: EmbeddingProvider | None = None,
    embedding_batch_size: int = 32,
) -> ServiceContainer:
    vault_path.mkdir(parents=True, exist_ok=True)
    state_path.mkdir(parents=True, exist_ok=True)
    opened = open_recoverable_database(state_path / "memory.db")
    database = opened.database
    repository = VaultRepository(vault_path, state_path / "audit.jsonl")
    indexer = Indexer(vault_path, database)
    index_jobs = IndexJobQueue(database, indexer)
    index_jobs.reconcile()
    index_jobs.process_due()
    if opened.recovered_from is not None:
        database.connection.execute(
            "INSERT INTO index_events(operation, path, status, error_code, details_json, created_at) "
            "VALUES ('recovery', NULL, 'completed', 'INDEX_CORRUPT', ?, datetime('now'))",
            (json.dumps({"quarantined": opened.recovered_from.name}),),
        )
    mutations = SQLiteMutationStore(database)
    vectors = SqliteVecStore(database)
    embedding_indexer = EmbeddingIndexer(database, vectors)
    if embedding_provider is not None:
        embedding_indexer.sync(embedding_provider, batch_size=embedding_batch_size)

    def on_change(paths: list[str]) -> None:
        for relative in paths:
            indexer.index_path(Path(relative))
        if embedding_provider is not None:
            embedding_indexer.sync(embedding_provider, batch_size=embedding_batch_size)

    if embedding_provider is not None:

        def sync_after_index(_path: Path) -> None:
            embedding_indexer.sync(embedding_provider, batch_size=embedding_batch_size)

        index_jobs.on_indexed = sync_after_index

    memory = MemoryService(repository, mutation_store=mutations, on_change=on_change)
    project_registry = SQLiteProjectRegistry(database)
    projects = ProjectService(project_registry)
    search = SearchService(
        database,
        indexer,
        embedding_provider=embedding_provider,
        vectors=vectors,
        project_detector=ProjectDetector(project_registry),
        vault_name=vault_path.name,
    )
    context = ContextPacker(search)
    return ServiceContainer(
        vault_path=vault_path,
        state_path=state_path,
        database=database,
        repository=repository,
        indexer=indexer,
        memory=memory,
        projects=projects,
        search=search,
        context=context,
        mutations=mutations,
        vectors=vectors,
        embedding_indexer=embedding_indexer,
        embedding_provider=embedding_provider,
        index_jobs=index_jobs,
        transport=transport,
        vault_name=vault_path.name,
    )


def _status(container: ServiceContainer) -> dict[str, Any]:
    document_count = container.database.connection.execute(
        "SELECT COUNT(*) FROM documents WHERE deleted_at IS NULL"
    ).fetchone()[0]
    chunk_count = container.database.connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    pending = container.database.connection.execute(
        "SELECT COUNT(*) FROM embedding_jobs WHERE status='pending'"
    ).fetchone()[0]
    unresolved_embeddings = container.database.connection.execute(
        "SELECT COUNT(*) FROM embedding_jobs WHERE status IN ('pending', 'failed')"
    ).fetchone()[0]
    invalid = container.database.connection.execute(
        "SELECT COUNT(DISTINCT path) FROM index_events WHERE error_code='NOTE_INVALID'"
    ).fetchone()[0]
    last_error = container.database.connection.execute(
        "SELECT error_code, path, created_at FROM index_events WHERE status='failed' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    duplicates: dict[str, Any] = {}
    try:
        container.repository.list_memories()
    except GlobalMemoryError as exc:
        if exc.code is ErrorCode.DUPLICATE_ID:
            duplicates = exc.details.get("duplicates", {})
    return {
        "package_version": __version__,
        "daemon_version": __version__,
        "contract_version": CONTRACT_VERSION,
        "vault_path": str(container.vault_path),
        "vault_valid": container.vault_path.is_dir(),
        "document_count": document_count,
        "chunk_count": chunk_count,
        "pending_index_jobs": container.database.connection.execute(
            "SELECT COUNT(*) FROM index_jobs WHERE status='pending'"
        ).fetchone()[0],
        "pending_embedding_jobs": pending,
        "watcher_state": container.watcher_state,
        "embedding_state": "configured" if container.embedding_provider is not None else "not_configured",
        "vector_state": "available" if container.vectors.available else "unavailable",
        "duplicate_id_conflicts": duplicates,
        "invalid_note_count": invalid,
        "last_indexing_error": dict(last_error) if last_error else None,
        "keyword_only": container.embedding_provider is None
        or not container.vectors.available
        or unresolved_embeddings > 0,
        "transport": container.transport,
    }


def _tag_cursor(snapshot: str, count: int, tag: str) -> str:
    payload = json.dumps({"snapshot": snapshot, "count": count, "tag": tag}, sort_keys=True).encode()
    signature = hashlib.sha256(b"tags:" + payload).hexdigest()[:16].encode()
    return base64.urlsafe_b64encode(signature + b"." + payload).decode().rstrip("=")


def _decode_tag_cursor(cursor: str, snapshot: str) -> tuple[int, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        signature, payload = raw.split(b".", 1)
        if signature != hashlib.sha256(b"tags:" + payload).hexdigest()[:16].encode():
            raise ValueError("signature")
        value = json.loads(payload)
        if value["snapshot"] != snapshot:
            raise GlobalMemoryError(ErrorCode.VERSION_CONFLICT, "The tag index changed during pagination.")
        return int(value["count"]), str(value["tag"])
    except GlobalMemoryError:
        raise
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The tag cursor is invalid.") from exc


def _tags(container: ServiceContainer, arguments: dict[str, Any]) -> dict[str, Any]:
    conditions = ["d.deleted_at IS NULL", "d.status = ?"]
    parameters: list[Any] = [arguments.get("status") or "active"]
    if arguments.get("scope"):
        conditions.append("d.scope = ?")
        parameters.append(arguments["scope"])
    project = arguments.get("project")
    if project:
        conditions.append("(d.scope IN ('global','organization') OR d.project = ?)")
        parameters.append(project)
    else:
        conditions.append("d.scope IN ('global','organization')")
    if arguments.get("prefix"):
        conditions.append("LOWER(tags.value) LIKE LOWER(?)")
        parameters.append(f"{arguments['prefix']}%")
    rows = container.database.connection.execute(
        f"""
        SELECT tags.value AS tag, COUNT(*) AS usage_count
        FROM documents d, json_each(d.metadata_json, '$.tags') tags
        WHERE {" AND ".join(conditions)}
        GROUP BY tags.value ORDER BY usage_count DESC, tag COLLATE NOCASE
        """,
        parameters,
    ).fetchall()
    snapshot = hashlib.sha256("|".join(f"{row['tag']}:{row['usage_count']}" for row in rows).encode()).hexdigest()[:16]
    if arguments.get("cursor"):
        count, tag = _decode_tag_cursor(arguments["cursor"], snapshot)
        rows = [row for row in rows if row["usage_count"] < count or (row["usage_count"] == count and row["tag"] > tag)]
    limit = min(int(arguments.get("limit", 50)), 100)
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit and page:
        next_cursor = _tag_cursor(snapshot, page[-1]["usage_count"], page[-1]["tag"])
    return {
        "tags": [{"tag": row["tag"], "usage_count": row["usage_count"]} for row in page],
        "next_cursor": next_cursor,
    }


def _documents(container: ServiceContainer, *, where: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = container.database.connection.execute(
        f"SELECT id, path, title, type, scope, project, status, updated_at FROM documents "
        f"WHERE deleted_at IS NULL AND {where} ORDER BY updated_at DESC, id LIMIT 100",
        parameters,
    ).fetchall()
    return [dict(row) for row in rows]


def _project_action(container: ServiceContainer, arguments: dict[str, Any]) -> dict[str, Any]:
    action = arguments["action"]
    payload = arguments.get("payload") or {}
    if action == "list":
        return {"projects": _jsonable(container.projects.list())}
    if action == "get":
        identifier = payload.get("id") or payload.get("name")
        if not isinstance(identifier, str):
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Project get requires an id or name.")
        return {"project": _jsonable(container.projects.get(identifier))}
    if action == "detect":
        detected = container.projects.detect(
            Path(payload["working_directory"]) if payload.get("working_directory") else None,
            payload.get("project"),
        )
        return {"detection": _jsonable(detected)}
    request_id = arguments.get("request_id")
    if not request_id:
        raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Mutating project actions require request_id.")

    def mutate() -> Any:
        if action == "add":
            return {"project": _jsonable(container.projects.add(ProjectDraft.model_validate(payload)))}
        identifier = payload.get("id") or payload.get("name")
        if not isinstance(identifier, str):
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Project mutation requires an id or name.")
        if action == "update":
            return {"project": _jsonable(container.projects.update(identifier, payload.get("patch") or {}))}
        if action == "deactivate":
            return {"project": _jsonable(container.projects.deactivate(identifier))}
        raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unsupported project action.")

    return container.guard.execute(request_id, f"projects:{action}", payload, mutate)


def _dispatch(container: ServiceContainer, name: str, arguments: dict[str, Any]) -> tuple[Any, list[str]]:
    verbose = bool(arguments.pop("verbose", False))
    diagnostics = ["verbose_requested"] if verbose else []
    if name == "memory_search":
        page = container.search.search(SearchRequest.model_validate(arguments))
        return _jsonable(page), list(page.warnings)
    if name == "memory_context":
        bundle = container.context.pack(**arguments)
        return _jsonable(bundle), list(bundle.warnings)
    if name == "memory_get":
        return _jsonable(container.memory.get(arguments["id"])), diagnostics
    if name == "memory_remember":
        request_id = arguments.pop("request_id")
        force = bool(arguments.pop("force", False))
        working_directory = arguments.pop("working_directory", None)
        if arguments.get("scope") == "project":
            detection = container.projects.detect(
                Path(working_directory) if working_directory else None,
                arguments.get("project"),
            )
            if detection.project is None:
                raise GlobalMemoryError(
                    ErrorCode.PROJECT_NOT_FOUND,
                    "A project-scoped memory requires a configured project or detectable working directory.",
                )
            arguments["project"] = detection.project.name
        draft = MemoryDraft.model_validate({**arguments, "content": arguments.pop("content")})
        return _jsonable(container.memory.remember(draft, request_id=request_id, force=force)), diagnostics
    if name == "memory_update":
        return _jsonable(
            container.memory.update(
                arguments["id"],
                arguments["expected_updated_at"],
                request_id=arguments["request_id"],
                metadata_patch=arguments.get("metadata_patch"),
                body=arguments.get("body"),
                section_patch=arguments.get("section_patch"),
            )
        ), diagnostics
    if name == "memory_approve":
        return _jsonable(
            container.memory.approve(
                arguments["id"],
                arguments.get("expected_updated_at"),
                request_id=arguments["request_id"],
                destination_override=arguments.get("destination_override"),
            )
        ), diagnostics
    if name == "memory_reject":
        return _jsonable(
            container.memory.reject(
                arguments["id"],
                arguments.get("expected_updated_at"),
                reason=arguments["reason"],
                request_id=arguments["request_id"],
            )
        ), diagnostics
    if name == "memory_supersede":
        replacement = MemoryDraft.model_validate(arguments["replacement"]) if arguments.get("replacement") else None
        return _jsonable(
            container.memory.supersede(
                arguments["old_id"],
                reason=arguments["reason"],
                request_id=arguments["request_id"],
                replacement_id=arguments.get("replacement_id"),
                replacement=replacement,
            )
        ), diagnostics
    if name == "memory_archive":
        return _jsonable(
            container.memory.archive(
                arguments["id"],
                reason=arguments["reason"],
                request_id=arguments["request_id"],
                hard_delete=arguments.get("hard_delete", False),
            )
        ), diagnostics
    if name == "memory_status":
        return _status(container), diagnostics
    if name == "memory_reindex":
        payload = {"full": arguments.get("full", False), "paths": arguments.get("paths") or []}

        def reindex() -> Any:
            if payload["full"]:
                return _jsonable(container.indexer.full_reindex())
            results: dict[str, str] = {}
            for raw_path in payload["paths"]:
                safe_vault_path(container.vault_path, Path(raw_path))
                results[raw_path] = container.indexer.index_path(Path(raw_path))
            return {"paths": results, "indexed": sum(result == "indexed" for result in results.values())}

        return container.guard.execute(arguments["request_id"], "reindex", payload, reindex), diagnostics
    if name == "memory_open":
        memory = container.memory.get(arguments["id"])
        path = memory.relative_path.as_posix()
        return {
            "id": memory.metadata.id,
            "path": str(memory.path),
            "relative_path": path,
            "obsidian_uri": (
                f"obsidian://open?vault={quote(container.vault_name, safe='')}&file={quote(path, safe='')}"
            ),
        }, diagnostics
    if name == "memory_dashboard_open":
        if container.dashboard_launcher is None:
            raise GlobalMemoryError(
                ErrorCode.DAEMON_UNAVAILABLE,
                "The dashboard is available only through the shared HTTP daemon.",
                remediation="Start the daemon and call memory_dashboard_open through its configured MCP transport.",
            )
        return container.dashboard_launcher(bool(arguments.get("open_browser", True))), diagnostics
    if name == "memory_projects":
        return _project_action(container, arguments), diagnostics
    if name == "memory_tags":
        return _tags(container, arguments), diagnostics
    raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unknown MCP tool.", details={"tool": name})


def _resource(container: ServiceContainer, uri: str) -> Any:
    if uri == "memory://v1/status":
        return _status(container)
    if uri == "memory://v1/projects":
        return {"projects": _jsonable(container.projects.list())}
    if uri == "memory://v1/candidates":
        return {"memories": _documents(container, where="status='candidate'")}
    if uri == "memory://v1/recent":
        return {"memories": _documents(container, where="status='active' AND scope IN ('global','organization')")}
    if uri == "memory://v1/tags":
        return _tags(container, {})
    prefix = "memory://v1/note/"
    if uri.startswith(prefix):
        return _jsonable(container.memory.get(unquote(uri.removeprefix(prefix))))
    project_prefix = "memory://v1/project/"
    if uri.startswith(project_prefix):
        rest = unquote(uri.removeprefix(project_prefix))
        project_name, _, suffix = rest.partition("/")
        if not suffix:
            return {"project": _jsonable(container.projects.get(project_name))}
        if suffix == "recent":
            return {
                "memories": _documents(container, where="status='active' AND project=?", parameters=(project_name,))
            }
        if suffix == "decisions":
            return {
                "memories": _documents(
                    container, where="status='active' AND project=? AND type='decision'", parameters=(project_name,)
                )
            }
        if suffix == "open-problems":
            return {
                "memories": _documents(
                    container, where="status='active' AND project=? AND type='solution'", parameters=(project_name,)
                )
            }
    raise GlobalMemoryError(ErrorCode.NOTE_NOT_FOUND, "The memory resource does not exist.", details={"uri": uri})


def create_mcp_server(container: ServiceContainer) -> Server[Any]:
    discovery = load_discovery()
    server: Server[Any] = Server("global-memory", version=__version__)
    tools_by_name = {item["name"]: item for item in discovery["tools"]}

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=item["name"],
                description=item["description"],
                inputSchema=item["inputSchema"],
                outputSchema=item["outputSchema"],
                _meta={"contract_version": CONTRACT_VERSION},
            )
            for item in discovery["tools"]
        ]

    @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        try:
            definition = tools_by_name.get(name)
            if definition is None:
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unknown MCP tool.", details={"tool": name})
            try:
                jsonschema.validate(arguments, definition["inputSchema"])
            except jsonschema.ValidationError as exc:
                raise GlobalMemoryError(
                    ErrorCode.NOTE_INVALID,
                    "The MCP tool arguments are invalid.",
                    details={"path": list(exc.absolute_path), "reason": exc.message},
                    remediation="Correct the arguments using the discovered input schema.",
                ) from exc
            data, warnings = _dispatch(container, name, dict(arguments))
            envelope = success(data, warnings=warnings)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
                structuredContent=envelope,
                isError=False,
            )
        except (GlobalMemoryError, ValidationError) as exc:
            error = (
                exc
                if isinstance(exc, GlobalMemoryError)
                else GlobalMemoryError(
                    ErrorCode.NOTE_INVALID, "The request payload is invalid.", details={"errors": exc.errors()}
                )
            )
            envelope = _jsonable(failure(error))
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
                structuredContent=envelope,
                isError=True,
            )
        except Exception:
            envelope = _jsonable(
                failure(
                    GlobalMemoryError(
                        ErrorCode.INTERNAL_ERROR,
                        "The memory service encountered an internal error.",
                        retryable=False,
                        remediation="Run `global-memory doctor` and inspect local structured logs.",
                    )
                )
            )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(envelope))],
                structuredContent=envelope,
                isError=True,
            )

    resource_items = discovery["resources"]

    @server.list_resources()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_resources() -> list[types.Resource]:
        return [
            types.Resource(
                name=item["name"],
                uri=AnyUrl(item["uriTemplate"]),
                description=item["description"],
                mimeType=item["mimeType"],
                _meta={"contract_version": CONTRACT_VERSION},
            )
            for item in resource_items
            if "{" not in item["uriTemplate"]
        ]

    @server.list_resource_templates()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_resource_templates() -> list[types.ResourceTemplate]:
        return [
            types.ResourceTemplate(
                name=item["name"],
                uriTemplate=item["uriTemplate"],
                description=item["description"],
                mimeType=item["mimeType"],
                _meta={"contract_version": CONTRACT_VERSION},
            )
            for item in resource_items
            if "{" in item["uriTemplate"]
        ]

    @server.read_resource()  # type: ignore[no-untyped-call,untyped-decorator]
    async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        try:
            envelope = success(_resource(container, str(uri)))
        except GlobalMemoryError as exc:
            envelope = failure(exc)
        return [ReadResourceContents(json.dumps(envelope, ensure_ascii=False), mime_type="application/json")]

    prompt_items = {item["name"]: item for item in discovery["prompts"]}

    @server.list_prompts()  # type: ignore[no-untyped-call,untyped-decorator]
    async def list_prompts() -> list[types.Prompt]:
        return [
            types.Prompt(
                name=item["name"],
                description=item["description"],
                arguments=[types.PromptArgument(**argument) for argument in item["arguments"]],
                _meta={"contract_version": CONTRACT_VERSION},
            )
            for item in discovery["prompts"]
        ]

    @server.get_prompt()  # type: ignore[no-untyped-call,untyped-decorator]
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> types.GetPromptResult:
        item = prompt_items.get(name)
        if item is None:
            raise ValueError("Unknown prompt")
        supplied = arguments or {}
        missing = [
            argument["name"]
            for argument in item["arguments"]
            if argument["required"] and not supplied.get(argument["name"])
        ]
        if missing:
            raise ValueError(f"Missing required prompt arguments: {', '.join(missing)}")
        text = f"{item['messageTemplate']}\n\nArguments: {json.dumps(supplied, ensure_ascii=False, sort_keys=True)}"
        return types.GetPromptResult(
            description=item["description"],
            messages=[types.PromptMessage(role="user", content=types.TextContent(type="text", text=text))],
        )

    return server
