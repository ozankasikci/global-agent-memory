"""Authenticated local dashboard routes and short-lived browser launch sessions."""

from __future__ import annotations

import json
import secrets
import uuid
import webbrowser
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from global_memory.domain.models import MemoryStatus, StoredMemory
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.mcp.contract import failure, success
from global_memory.operations import backup_vault
from global_memory.vault.paths import safe_component

DASHBOARD_COOKIE = "global_agent_memory_dashboard"
TICKET_TTL = timedelta(seconds=60)
SESSION_TTL = timedelta(hours=12)


class DashboardSessions:
    """Issue single-use launch tickets and HttpOnly local browser sessions."""

    def __init__(
        self,
        base_url: str,
        *,
        opener: Callable[[str], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.opener = opener or webbrowser.open
        self.clock = clock or (lambda: datetime.now(UTC))
        self._tickets: dict[str, datetime] = {}
        self._sessions: dict[str, datetime] = {}

    def _purge(self) -> None:
        now = self.clock()
        self._tickets = {token: expires for token, expires in self._tickets.items() if expires > now}
        self._sessions = {token: expires for token, expires in self._sessions.items() if expires > now}

    def launch(self, open_browser: bool = True) -> dict[str, Any]:
        self._purge()
        ticket = secrets.token_urlsafe(32)
        self._tickets[ticket] = self.clock() + TICKET_TTL
        url = f"{self.base_url}/ui/session?ticket={quote(ticket, safe='')}"
        opened = self.opener(url) if open_browser else False
        return {"url": url, "opened": opened, "expires_in_seconds": int(TICKET_TTL.total_seconds())}

    def exchange(self, ticket: str) -> str | None:
        self._purge()
        expires = self._tickets.pop(ticket, None)
        if expires is None or expires <= self.clock():
            return None
        session = secrets.token_urlsafe(32)
        self._sessions[session] = self.clock() + SESSION_TTL
        return session

    def valid(self, session: str | None) -> bool:
        self._purge()
        return bool(session and session in self._sessions)


def _dashboard_root() -> Path:
    packaged = Path(__file__).resolve().parent / "_dashboard"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "dashboard" / "dist"


def _extract_section(body: str, heading: str) -> str | None:
    lines = body.splitlines()
    capture = False
    values: list[str] = []
    for line in lines:
        if line.startswith("#"):
            title = line.lstrip("#").strip().casefold()
            if capture:
                break
            capture = title == heading.casefold()
            continue
        if capture:
            values.append(line)
    value = "\n".join(values).strip()
    return value or None


def _summary(body: str) -> str:
    explicit = _extract_section(body, "Summary")
    if explicit:
        return " ".join(explicit.split())[:360]
    paragraphs = [
        " ".join(part.split()) for part in body.split("\n\n") if part.strip() and not part.lstrip().startswith("#")
    ]
    return (paragraphs[0] if paragraphs else "")[:360]


def _related(memory: StoredMemory, memories: list[StoredMemory]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if memory.metadata.status is not MemoryStatus.CANDIDATE or memory.metadata.visibility.value == "sealed":
        return [], []
    duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for other in memories:
        if (
            other.metadata.id == memory.metadata.id
            or other.metadata.status is not MemoryStatus.ACTIVE
            or other.metadata.visibility.value == "sealed"
        ):
            continue
        title_score = SequenceMatcher(None, memory.metadata.title.casefold(), other.metadata.title.casefold()).ratio()
        shared_tags = set(memory.metadata.tags) & set(other.metadata.tags)
        if title_score >= 0.62 or (len(shared_tags) >= 2 and title_score >= 0.4):
            duplicates.append(
                {
                    "id": other.metadata.id,
                    "title": other.metadata.title,
                    "excerpt": _summary(other.body),
                    "similarity": round(title_score, 3),
                    "status": other.metadata.status.value,
                }
            )
        if other.metadata.id in memory.metadata.links:
            conflicts.append(
                {
                    "id": other.metadata.id,
                    "title": other.metadata.title,
                    "excerpt": _summary(other.body),
                    "status": other.metadata.status.value,
                }
            )
    return sorted(duplicates, key=lambda item: item["similarity"], reverse=True)[:3], conflicts[:3]


def serialize_memory(
    memory: StoredMemory,
    memories: list[StoredMemory],
    *,
    unlock_sealed: bool = False,
) -> dict[str, Any]:
    duplicates, conflicts = _related(memory, memories)
    metadata = memory.metadata
    sealed = metadata.visibility.value == "sealed" and not unlock_sealed
    return {
        "id": metadata.id,
        "title": "Sealed memory" if sealed else metadata.title,
        "type": metadata.type,
        "scope": metadata.scope.value,
        "project": metadata.project,
        "status": metadata.status.value,
        "visibility": metadata.visibility.value,
        "access_policy": metadata.access_policy,
        "allowed_projects": metadata.allowed_projects,
        "max_permission": metadata.max_permission.value,
        "confidence": metadata.confidence,
        "importance": metadata.importance,
        "created_at": metadata.created_at.isoformat(),
        "updated_at": metadata.updated_at.isoformat(),
        "tags": [] if sealed else metadata.tags,
        "links": [] if sealed else metadata.links,
        "source_kind": metadata.source_kind,
        "source_ref": metadata.source_ref,
        "body": "" if sealed else memory.body,
        "summary": "Unlock once to view this memory. Access will be recorded." if sealed else _summary(memory.body),
        "evidence": None if sealed else _extract_section(memory.body, "Evidence"),
        "path": "" if sealed else str(memory.path),
        "relative_path": "" if sealed else memory.relative_path.as_posix(),
        "version": memory.version,
        "possible_duplicates": duplicates,
        "conflicts": conflicts,
    }


def _activity(
    container: Any,
    memories: list[StoredMemory],
    selected_project: str | None = None,
) -> list[dict[str, Any]]:
    by_id = {memory.metadata.id: memory for memory in memories}
    try:
        lines = container.repository.audit_path.read_text().splitlines()[-100:]
    except OSError:
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        memory = by_id.get(str(record.get("memory_id")))
        details = record.get("details") if isinstance(record.get("details"), dict) else {}
        project = details.get("project") or (memory.metadata.project if memory is not None else None)
        path_project: str | None = None
        relative_path = Path(str(record.get("relative_path", "")))
        if len(relative_path.parts) >= 2 and relative_path.parts[0] == "20 Projects":
            path_project = relative_path.parts[1]
        if selected_project is not None:
            is_selected = project == selected_project or (
                project is None and path_project == safe_component(selected_project)
            )
            if not is_selected:
                continue
        event = str(record.get("event", "changed"))
        action = event.removeprefix("memory_").removesuffix("_created").replace("_", " ")
        records.append(
            {
                "actor": "memory service",
                "action": action,
                "target": memory.metadata.title if memory is not None else str(record.get("memory_id", "memory")),
                "created_at": str(record.get("at", "")),
                "kind": event,
            }
        )
    return records[:50]


def _services(container: Any, status: dict[str, Any]) -> list[dict[str, str]]:
    claude_skill = Path.home() / ".claude/skills/global-memory/SKILL.md"
    codex_skill = Path.home() / ".agents/skills/global-memory/SKILL.md"
    semantic_ok = status["embedding_state"] == "configured" and not status["keyword_only"]
    return [
        {"name": "Local daemon", "detail": "localhost only · private", "state": "operational"},
        {
            "name": "Claude Code",
            "detail": "skill installed" if claude_skill.exists() else "integration not installed",
            "state": "operational" if claude_skill.exists() else "down",
        },
        {
            "name": "Codex",
            "detail": "skill installed" if codex_skill.exists() else "integration not installed",
            "state": "operational" if codex_skill.exists() else "down",
        },
        {
            "name": "Ollama",
            "detail": "semantic retrieval available" if semantic_ok else "keyword fallback active",
            "state": "operational" if semantic_ok else "degraded",
        },
    ]


def _error_response(error: GlobalMemoryError, *, status_code: int = 400) -> JSONResponse:
    return JSONResponse(failure(error), status_code=status_code)


async def _dashboard_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The dashboard action payload is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "The dashboard action payload must be an object.")
    return payload


def _classification_patch(container: Any, memory: StoredMemory, payload: dict[str, Any]) -> dict[str, Any]:
    visibility = str(payload["visibility"])
    if visibility not in {"standard", "protected", "sealed"}:
        raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unsupported memory visibility.")
    if visibility == "protected":
        access_policy = str(payload.get("access_policy") or "user_approval")
        allowed_projects = list(payload.get("allowed_projects") or [])
        max_permission = str(payload.get("max_permission") or "read")
        if memory.metadata.scope.value == "project":
            allowed_projects = [memory.metadata.project] if memory.metadata.project else []
        else:
            known_projects = {project.name for project in container.projects.list()}
            unknown = sorted(set(allowed_projects) - known_projects)
            if unknown:
                raise GlobalMemoryError(
                    ErrorCode.PROJECT_NOT_FOUND,
                    "The access policy contains an unknown project.",
                    details={"projects": unknown},
                )
    elif visibility == "sealed":
        access_policy = "per_access"
        allowed_projects = []
        max_permission = "read"
    else:
        access_policy = "user_approval"
        allowed_projects = []
        max_permission = "read"
    return {
        "visibility": visibility,
        "access_policy": access_policy,
        "allowed_projects": allowed_projects,
        "max_permission": max_permission,
    }


def dashboard_routes(container: Any, sessions: DashboardSessions) -> list[Any]:
    """Build local UI, session, and lifecycle API routes for one daemon container."""

    root = _dashboard_root()

    def authenticated(request: Request) -> bool:
        return sessions.valid(request.cookies.get(DASHBOARD_COOKIE))

    def mutation_allowed(request: Request) -> bool:
        return authenticated(request) and request.headers.get("X-GAM-Action") == "dashboard"

    async def index(_request: Request) -> Response:
        path = root / "index.html"
        if not path.is_file():
            return _error_response(
                GlobalMemoryError(
                    ErrorCode.DAEMON_UNAVAILABLE,
                    "Dashboard assets are not installed.",
                    remediation="Build the dashboard assets and reinstall Global Agent Memory.",
                ),
                status_code=503,
            )
        response = FileResponse(path)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
                    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            }
        )
        return response

    async def root_redirect(_request: Request) -> Response:
        return RedirectResponse("/ui/", status_code=307)

    async def exchange(request: Request) -> Response:
        session = sessions.exchange(request.query_params.get("ticket", ""))
        if session is None:
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard launch ticket is invalid or expired."),
                status_code=401,
            )
        response = RedirectResponse("/ui/", status_code=303)
        response.set_cookie(
            DASHBOARD_COOKIE,
            session,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True,
            samesite="strict",
            secure=False,
            path="/ui",
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    async def bootstrap(request: Request) -> Response:
        if not authenticated(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "A dashboard session is required."), status_code=401
            )
        try:
            all_memories = container.memory.list_memories()
            projects = container.projects.list()
            requested = request.query_params.get("project")
            selected = requested or (projects[0].name if projects else None)
            memories = [
                memory
                for memory in all_memories
                if memory.metadata.scope.value in {"global", "organization"}
                or selected is None
                or memory.metadata.project == selected
            ]
            serialized = [serialize_memory(memory, all_memories) for memory in memories]
            status = container_status(container)
            data = {
                "projects": [project.model_dump(mode="json") for project in projects],
                "project_stats": {
                    project.name: {
                        "memories": sum(
                            (
                                memory.metadata.project == project.name
                                or memory.metadata.scope.value in {"global", "organization"}
                            )
                            and memory.metadata.status is not MemoryStatus.CANDIDATE
                            for memory in all_memories
                        ),
                        "candidates": sum(
                            (
                                memory.metadata.project == project.name
                                or memory.metadata.scope.value in {"global", "organization"}
                            )
                            and memory.metadata.status is MemoryStatus.CANDIDATE
                            for memory in all_memories
                        ),
                    }
                    for project in projects
                },
                "selected_project": selected,
                "memories": serialized,
                "candidates": [memory for memory in serialized if memory["status"] == "candidate"],
                "status": status,
                "services": _services(container, status),
                "activity": _activity(container, all_memories, selected),
                "access": container.access.dashboard_state()
                if container.access is not None
                else {"requests": [], "grants": [], "events": []},
            }
            return JSONResponse(success(data))
        except GlobalMemoryError as error:
            return _error_response(error)

    async def mutate(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        try:
            payload = await _dashboard_payload(request)
            memory_id = request.path_params["memory_id"]
            action = request.path_params.get("action")
            request_id = str(uuid.uuid4())
            if request.method == "PATCH":
                result = container.memory.update(
                    memory_id,
                    str(payload["expected_updated_at"]),
                    request_id=request_id,
                    metadata_patch=payload.get("metadata_patch"),
                    body=payload.get("body"),
                )
            elif action == "approve":
                expected_updated_at = payload.get("expected_updated_at")
                if "visibility" in payload:
                    memory = container.memory.get(memory_id)
                    classified = container.memory.update(
                        memory_id,
                        str(expected_updated_at),
                        request_id=request_id,
                        metadata_patch=_classification_patch(container, memory, payload),
                    )
                    expected_updated_at = classified.metadata.updated_at.isoformat()
                    request_id = str(uuid.uuid4())
                result = container.memory.approve(
                    memory_id,
                    expected_updated_at,
                    request_id=request_id,
                )
            elif action == "reject":
                result = container.memory.reject(
                    memory_id,
                    payload.get("expected_updated_at"),
                    reason=str(payload["reason"]),
                    request_id=request_id,
                )
            elif action == "archive":
                result = container.memory.archive(
                    memory_id,
                    reason=str(payload.get("reason") or "Archived from dashboard"),
                    request_id=request_id,
                )
            else:
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unsupported dashboard memory action.")
            all_memories = container.memory.list_memories()
            return JSONResponse(success(serialize_memory(result, all_memories)))
        except KeyError as error:
            return _error_response(
                GlobalMemoryError(
                    ErrorCode.NOTE_INVALID, "A required dashboard field is missing.", details={"field": str(error)}
                )
            )
        except (GlobalMemoryError, ValidationError) as error:
            mapped = (
                error
                if isinstance(error, GlobalMemoryError)
                else GlobalMemoryError(
                    ErrorCode.NOTE_INVALID,
                    "The dashboard action is invalid.",
                    details={"errors": error.errors(include_context=False)},
                )
            )
            status_code = 409 if mapped.code is ErrorCode.VERSION_CONFLICT else 400
            return _error_response(mapped, status_code=status_code)

    async def reindex(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        report = container.indexer.full_reindex()
        return JSONResponse(success(asdict(report)))

    async def backup(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        name = f"global-agent-memory-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.zip"
        destination = backup_vault(container.vault_path, container.state_path / "backups" / name)
        return JSONResponse(success({"path": str(destination)}))

    async def classify(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        try:
            payload = await _dashboard_payload(request)
            memory = container.memory.get(request.path_params["memory_id"])
            result = container.memory.update(
                memory.metadata.id,
                str(payload["expected_updated_at"]),
                request_id=str(uuid.uuid4()),
                metadata_patch=_classification_patch(container, memory, payload),
            )
            if container.access is not None:
                container.access.reconcile_memory_policy(result.metadata.id)
            return JSONResponse(success(serialize_memory(result, container.memory.list_memories())))
        except KeyError as error:
            return _error_response(
                GlobalMemoryError(
                    ErrorCode.NOTE_INVALID, "A classification field is missing.", details={"field": str(error)}
                )
            )
        except (GlobalMemoryError, ValidationError) as error:
            mapped = (
                error
                if isinstance(error, GlobalMemoryError)
                else GlobalMemoryError(
                    ErrorCode.NOTE_INVALID,
                    "The classification is invalid.",
                    details={"errors": error.errors(include_context=False)},
                )
            )
            return _error_response(mapped, status_code=409 if mapped.code is ErrorCode.VERSION_CONFLICT else 400)

    async def unlock_sealed(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        try:
            payload = await _dashboard_payload(request)
            purpose = str(payload.get("purpose") or "Owner review")
            memory = container.memory.get(request.path_params["memory_id"])
            if memory.metadata.visibility.value != "sealed":
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "This memory is not sealed.")
            if container.access is not None:
                container.access.record_sealed_unlock(memory_id=memory.metadata.id, purpose=purpose)
            return JSONResponse(success(serialize_memory(memory, container.memory.list_memories(), unlock_sealed=True)))
        except GlobalMemoryError as error:
            return _error_response(error, status_code=404 if error.code is ErrorCode.NOTE_NOT_FOUND else 400)

    async def access_action(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        if container.access is None:
            return _error_response(
                GlobalMemoryError(ErrorCode.DAEMON_UNAVAILABLE, "Access approvals are unavailable."), status_code=503
            )
        try:
            payload = await _dashboard_payload(request)
            action = request.path_params["action"]
            identifier = request.path_params["identifier"]
            if action == "approve":
                result = container.access.approve(
                    identifier,
                    duration=str(payload.get("duration") or "once"),
                    permission=str(payload.get("permission") or "read"),
                    memory_ids=[str(memory_id) for memory_id in payload.get("memory_ids") or []],
                )
            elif action == "deny":
                result = container.access.deny(identifier, reason=str(payload.get("reason") or "Denied by owner"))
            elif action == "revoke":
                result = container.access.revoke(identifier)
            else:
                raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unsupported access action.")
            return JSONResponse(success({"result": result, "access": container.access.dashboard_state()}))
        except GlobalMemoryError as error:
            return _error_response(error, status_code=409 if error.code is ErrorCode.VERSION_CONFLICT else 400)

    async def open_obsidian(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        try:
            memory = container.memory.get(request.path_params["memory_id"])
        except GlobalMemoryError as error:
            return _error_response(error, status_code=404)
        if memory.metadata.visibility.value == "sealed":
            return _error_response(
                GlobalMemoryError(
                    ErrorCode.ACCESS_APPROVAL_REQUIRED,
                    "Unlock the sealed memory in the dashboard first.",
                ),
                status_code=403,
            )
        path = memory.relative_path.as_posix()
        uri = f"obsidian://open?vault={quote(container.vault_name, safe='')}&file={quote(path, safe='')}"
        webbrowser.open(uri)
        return JSONResponse(success({"obsidian_uri": uri}))

    async def open_file(request: Request) -> Response:
        if not mutation_allowed(request):
            return _error_response(
                GlobalMemoryError(ErrorCode.UNAUTHORIZED, "The dashboard action is unauthorized."), status_code=401
            )
        try:
            memory = container.memory.get(request.path_params["memory_id"])
        except GlobalMemoryError as error:
            return _error_response(error, status_code=404)
        if memory.metadata.visibility.value == "sealed":
            return _error_response(
                GlobalMemoryError(
                    ErrorCode.ACCESS_APPROVAL_REQUIRED,
                    "Unlock the sealed memory in the dashboard first.",
                ),
                status_code=403,
            )
        uri = memory.path.as_uri()
        webbrowser.open(uri)
        return JSONResponse(success({"file_uri": uri}))

    routes: list[Any] = [
        Route("/ui", root_redirect, methods=["GET"]),
        Route("/ui/", index, methods=["GET"]),
        Route("/ui/session", exchange, methods=["GET"]),
        Route("/ui/api/bootstrap", bootstrap, methods=["GET"]),
        Route("/ui/api/memories/{memory_id:str}", mutate, methods=["PATCH"]),
        Route("/ui/api/memories/{memory_id:str}/classify", classify, methods=["POST"]),
        Route("/ui/api/memories/{memory_id:str}/unlock", unlock_sealed, methods=["POST"]),
        Route("/ui/api/memories/{memory_id:str}/open-obsidian", open_obsidian, methods=["POST"]),
        Route("/ui/api/memories/{memory_id:str}/open-file", open_file, methods=["POST"]),
        Route("/ui/api/memories/{memory_id:str}/{action:str}", mutate, methods=["POST"]),
        Route("/ui/api/reindex", reindex, methods=["POST"]),
        Route("/ui/api/backup", backup, methods=["POST"]),
        Route("/ui/api/access/{identifier:str}/{action:str}", access_action, methods=["POST"]),
    ]
    assets = root / "assets"
    if assets.is_dir():
        routes.append(Mount("/ui/assets", app=StaticFiles(directory=assets), name="dashboard-assets"))
    return routes


def container_status(container: Any) -> dict[str, Any]:
    """Import the canonical status helper lazily to avoid a module cycle."""
    from global_memory.mcp.server import _status

    return _status(container)
