"""Fail-closed access requests, temporary grants, and content-free audit events."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.index.database import IndexDatabase
from global_memory.index.indexer import Indexer

PERMISSION_LEVEL = {"read": 1, "edit": 2, "manage": 3}
DURATION_LEVEL = {"once": 1, "15m": 2, "task": 3, "session": 4}
DURATION_TTLS = {
    "once": None,
    "15m": timedelta(minutes=15),
    "task": timedelta(hours=4),
    "session": timedelta(hours=12),
}


class AccessService:
    """Own capability-style grants; agents can request and poll but never approve."""

    def __init__(self, database: IndexDatabase, indexer: Indexer) -> None:
        self.database = database
        self.indexer = indexer

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _metadata(row: Any) -> dict[str, Any]:
        return json.loads(row["metadata_json"]) if row is not None else {}

    @staticmethod
    def _max_permission(metadata: dict[str, Any]) -> str:
        return str(metadata.get("max_permission") or metadata.get("default_permission") or "read")

    def _event(
        self,
        *,
        agent: str,
        action: str,
        purpose: str,
        permission: str,
        scope: str,
        actor: str,
        status: str,
        request_id: str | None = None,
        grant_id: str | None = None,
    ) -> None:
        self.database.connection.execute(
            "INSERT INTO access_events(request_id, grant_id, agent, action, purpose, permission, "
            "scope, actor, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                grant_id,
                agent,
                action,
                purpose,
                permission,
                scope,
                actor,
                status,
                self._now().isoformat(),
            ),
        )

    def request(
        self,
        *,
        agent: str,
        purpose: str,
        query: str,
        project: str | None,
        permission: str = "read",
        duration: str = "once",
    ) -> dict[str, Any]:
        if permission not in PERMISSION_LEVEL:
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Access permission must be read, edit, or manage.")
        if duration not in DURATION_TTLS:
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Access duration must be once, 15m, task, or session.")
        matches = self.indexer.keyword_search(
            query,
            applicable_project=project,
            apply_default_scope=True,
            visibilities=["protected"],
            statuses=["active"],
            limit=100,
        )
        matched_ids: list[str] = []
        for match in matches:
            row = self.database.connection.execute(
                "SELECT metadata_json FROM documents WHERE id=?", (match.memory_id,)
            ).fetchone()
            metadata = self._metadata(row)
            allowed_projects = metadata.get("allowed_projects") or []
            if allowed_projects and project not in allowed_projects:
                continue
            if match.memory_id not in matched_ids:
                matched_ids.append(match.memory_id)
        sealed_conditions = ["deleted_at IS NULL", "status='active'", "visibility='sealed'"]
        params: list[Any] = []
        if project:
            sealed_conditions.append("(scope IN ('global','organization') OR project=?)")
            params.append(project)
        else:
            sealed_conditions.append("scope IN ('global','organization')")
        sealed_count = int(
            self.database.connection.execute(
                f"SELECT COUNT(*) FROM documents WHERE {' AND '.join(sealed_conditions)}", params
            ).fetchone()[0]
        )
        request_id = f"req_{secrets.token_urlsafe(18)}"
        created_at = self._now().isoformat()
        with self.database.transaction():
            self.database.connection.execute(
                "INSERT INTO access_requests(id, agent, project, purpose, permission, requested_duration, query, "
                "matched_ids_json, sealed_match_count, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (
                    request_id,
                    agent.strip() or "unknown agent",
                    project,
                    purpose.strip(),
                    permission,
                    duration,
                    query,
                    json.dumps(matched_ids),
                    sealed_count,
                    created_at,
                ),
            )
            self._event(
                request_id=request_id,
                agent=agent.strip() or "unknown agent",
                action="requested",
                purpose=purpose.strip(),
                permission=permission,
                scope=f"{len(matched_ids)} protected matches",
                actor="agent",
                status="pending",
            )
        return {
            "request_id": request_id,
            "status": "pending",
            "message": "User approval is required. Poll memory_access_status with this request_id.",
        }

    def status(self, request_id: str) -> dict[str, Any]:
        row = self.database.connection.execute(
            "SELECT id, status, resolved_at, resolution_note FROM access_requests WHERE id=?", (request_id,)
        ).fetchone()
        if row is None:
            raise GlobalMemoryError(ErrorCode.NOTE_NOT_FOUND, "The access request does not exist.")
        result = dict(row)
        if row["status"] == "approved":
            grant = self.database.connection.execute(
                "SELECT id, permission, duration, expires_at, remaining_uses, status FROM access_grants "
                "WHERE request_id=? ORDER BY created_at DESC LIMIT 1",
                (request_id,),
            ).fetchone()
            if grant:
                result["grant"] = dict(grant)
        return result

    def approve(
        self,
        request_id: str,
        *,
        duration: str,
        permission: str,
        memory_ids: list[str],
    ) -> dict[str, Any]:
        if duration not in DURATION_LEVEL:
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unsupported access duration.")
        if permission not in PERMISSION_LEVEL:
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Unsupported access permission.")
        selected_ids = list(dict.fromkeys(memory_ids))
        if not selected_ids:
            raise GlobalMemoryError(ErrorCode.NOTE_INVALID, "Select at least one protected memory.")

        now = self._now()
        grant_id = f"grant_{secrets.token_urlsafe(24)}"
        with self.database.transaction():
            request = self.database.connection.execute(
                "SELECT * FROM access_requests WHERE id=?", (request_id,)
            ).fetchone()
            if request is None:
                raise GlobalMemoryError(ErrorCode.NOTE_NOT_FOUND, "The access request does not exist.")
            if request["status"] != "pending":
                raise GlobalMemoryError(ErrorCode.VERSION_CONFLICT, "The access request was already resolved.")
            if PERMISSION_LEVEL[permission] > PERMISSION_LEVEL[request["permission"]]:
                raise GlobalMemoryError(
                    ErrorCode.UNAUTHORIZED,
                    "Approval cannot elevate the permission requested by the agent.",
                )
            if DURATION_LEVEL[duration] > DURATION_LEVEL[request["requested_duration"]]:
                raise GlobalMemoryError(
                    ErrorCode.UNAUTHORIZED,
                    "Approval cannot last longer than the duration requested by the agent.",
                )

            matched_ids = set(json.loads(request["matched_ids_json"]))
            if not set(selected_ids) <= matched_ids:
                raise GlobalMemoryError(
                    ErrorCode.ACCESS_GRANT_INVALID,
                    "The approval includes a memory outside the original protected matches.",
                )
            placeholders = ",".join("?" for _ in selected_ids)
            rows = self.database.connection.execute(
                f"SELECT * FROM documents WHERE id IN ({placeholders}) AND deleted_at IS NULL",
                selected_ids,
            ).fetchall()
            documents = {row["id"]: row for row in rows}
            if set(documents) != set(selected_ids):
                raise GlobalMemoryError(ErrorCode.VERSION_CONFLICT, "A selected memory is no longer available.")
            for memory_id in selected_ids:
                document = documents[memory_id]
                if document["status"] != "active" or document["visibility"] != "protected":
                    raise GlobalMemoryError(
                        ErrorCode.VERSION_CONFLICT,
                        "A selected memory is no longer active and protected.",
                    )
                metadata = self._metadata(document)
                allowed_projects = metadata.get("allowed_projects") or []
                if allowed_projects and request["project"] not in allowed_projects:
                    raise GlobalMemoryError(
                        ErrorCode.ACCESS_GRANT_INVALID,
                        "A selected memory is not available to the request project.",
                    )
                if PERMISSION_LEVEL[permission] > PERMISSION_LEVEL[self._max_permission(metadata)]:
                    raise GlobalMemoryError(
                        ErrorCode.UNAUTHORIZED,
                        "The selected permission exceeds a memory's maximum permission.",
                    )
                if metadata.get("access_policy", "user_approval") == "per_access" and duration != "once":
                    raise GlobalMemoryError(
                        ErrorCode.UNAUTHORIZED,
                        "A selected memory requires approval for every retrieval.",
                    )

            ttl = DURATION_TTLS[duration]
            expires_at = (now + ttl).isoformat() if ttl else None
            remaining_uses = 1 if duration == "once" else None
            self.database.connection.execute(
                "UPDATE access_requests SET status='approved', resolved_at=? WHERE id=?",
                (now.isoformat(), request_id),
            )
            self.database.connection.execute(
                "INSERT INTO access_grants(id, request_id, agent, project, purpose, permission, scope_ids_json, "
                "duration, status, created_at, expires_at, remaining_uses) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                (
                    grant_id,
                    request_id,
                    request["agent"],
                    request["project"],
                    request["purpose"],
                    permission,
                    json.dumps(selected_ids),
                    duration,
                    now.isoformat(),
                    expires_at,
                    remaining_uses,
                ),
            )
            self._event(
                request_id=request_id,
                grant_id=grant_id,
                agent=request["agent"],
                action="granted",
                purpose=request["purpose"],
                permission=permission,
                scope=f"{len(selected_ids)} protected memories for {duration}",
                actor="owner",
                status="active",
            )
        return self.status(request_id)

    def deny(self, request_id: str, *, reason: str = "Denied by owner") -> dict[str, Any]:
        row = self.database.connection.execute("SELECT * FROM access_requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            raise GlobalMemoryError(ErrorCode.NOTE_NOT_FOUND, "The access request does not exist.")
        if row["status"] != "pending":
            raise GlobalMemoryError(ErrorCode.VERSION_CONFLICT, "The access request was already resolved.")
        with self.database.transaction():
            self.database.connection.execute(
                "UPDATE access_requests SET status='denied', resolved_at=?, resolution_note=? WHERE id=?",
                (self._now().isoformat(), reason, request_id),
            )
            self._event(
                request_id=request_id,
                agent=row["agent"],
                action="denied",
                purpose=row["purpose"],
                permission=row["permission"],
                scope="protected memories",
                actor="owner",
                status="denied",
            )
        return self.status(request_id)

    def _revoke_row(self, row: Any, *, action: str, actor: str = "owner") -> None:
        self.database.connection.execute("UPDATE access_grants SET status='revoked' WHERE id=?", (row["id"],))
        self._event(
            request_id=row["request_id"],
            grant_id=row["id"],
            agent=row["agent"],
            action=action,
            purpose=row["purpose"],
            permission=row["permission"],
            scope=f"{len(json.loads(row['scope_ids_json']))} protected memories",
            actor=actor,
            status="revoked",
        )

    def revoke(self, grant_id: str) -> dict[str, Any]:
        row = self.database.connection.execute("SELECT * FROM access_grants WHERE id=?", (grant_id,)).fetchone()
        if row is None:
            raise GlobalMemoryError(ErrorCode.NOTE_NOT_FOUND, "The access grant does not exist.")
        with self.database.transaction():
            self._revoke_row(row, action="revoked")
        return {"id": grant_id, "status": "revoked"}

    def _currently_allowed_ids(self, grant: Any, permission: str) -> set[str]:
        allowed: set[str] = set()
        for memory_id in json.loads(grant["scope_ids_json"]):
            document = self.database.connection.execute(
                "SELECT * FROM documents WHERE id=? AND deleted_at IS NULL", (memory_id,)
            ).fetchone()
            if document is None or document["status"] != "active" or document["visibility"] != "protected":
                continue
            metadata = self._metadata(document)
            projects = metadata.get("allowed_projects") or []
            if projects and grant["project"] not in projects:
                continue
            if PERMISSION_LEVEL[permission] > PERMISSION_LEVEL[self._max_permission(metadata)]:
                continue
            if metadata.get("access_policy", "user_approval") == "per_access" and grant["duration"] != "once":
                continue
            allowed.add(memory_id)
        return allowed

    def scope_for(
        self,
        grant_id: str,
        *,
        permission: str = "read",
        project: str | None = None,
        consume: bool = True,
    ) -> set[str]:
        row = self.database.connection.execute("SELECT * FROM access_grants WHERE id=?", (grant_id,)).fetchone()
        if row is None or row["status"] != "active":
            raise GlobalMemoryError(ErrorCode.ACCESS_GRANT_INVALID, "The access grant is invalid or inactive.")
        now = self._now()
        if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) <= now:
            self.database.connection.execute("UPDATE access_grants SET status='expired' WHERE id=?", (grant_id,))
            raise GlobalMemoryError(ErrorCode.ACCESS_GRANT_EXPIRED, "The access grant has expired.")
        if row["remaining_uses"] is not None and int(row["remaining_uses"]) <= 0:
            self.database.connection.execute("UPDATE access_grants SET status='used' WHERE id=?", (grant_id,))
            raise GlobalMemoryError(ErrorCode.ACCESS_GRANT_EXPIRED, "The one-time access grant was already used.")
        if PERMISSION_LEVEL[row["permission"]] < PERMISSION_LEVEL[permission]:
            raise GlobalMemoryError(ErrorCode.ACCESS_GRANT_INVALID, "The access grant lacks the required permission.")
        if row["project"] and project and row["project"] != project:
            raise GlobalMemoryError(ErrorCode.ACCESS_GRANT_INVALID, "The access grant is scoped to another project.")
        ids = self._currently_allowed_ids(row, permission)
        if not ids:
            raise GlobalMemoryError(
                ErrorCode.ACCESS_GRANT_INVALID,
                "The grant no longer covers a memory allowed by current policy.",
            )
        if consume and row["remaining_uses"] is not None:
            remaining = int(row["remaining_uses"]) - 1
            self.database.connection.execute(
                "UPDATE access_grants SET remaining_uses=?, status=? WHERE id=?",
                (remaining, "used" if remaining <= 0 else "active", grant_id),
            )
        if consume:
            self._event(
                request_id=row["request_id"],
                grant_id=grant_id,
                agent=row["agent"],
                action="used",
                purpose=row["purpose"],
                permission=permission,
                scope=f"{len(ids)} protected memories",
                actor="agent",
                status="completed",
            )
        return ids

    def authorize_memory(self, memory_id: str, visibility: str, grant_id: str | None, permission: str) -> None:
        if visibility == "standard":
            return
        if visibility == "sealed":
            raise GlobalMemoryError(
                ErrorCode.ACCESS_APPROVAL_REQUIRED,
                "This memory is sealed and cannot be accessed through agent tools.",
            )
        if not grant_id:
            raise GlobalMemoryError(
                ErrorCode.ACCESS_APPROVAL_REQUIRED,
                "This memory is protected. Request user approval before accessing it.",
            )
        if memory_id not in self.scope_for(grant_id, permission=permission):
            raise GlobalMemoryError(ErrorCode.ACCESS_GRANT_INVALID, "The grant does not cover this memory.")

    def reconcile_memory_policy(self, memory_id: str) -> None:
        """Revoke active grants whose selected memory no longer permits their policy."""
        grants = self.database.connection.execute(
            "SELECT DISTINCT g.* FROM access_grants g, json_each(g.scope_ids_json) scope "
            "WHERE g.status='active' AND scope.value=?",
            (memory_id,),
        ).fetchall()
        if not grants:
            return
        with self.database.transaction():
            for grant in grants:
                if memory_id not in self._currently_allowed_ids(grant, grant["permission"]):
                    self._revoke_row(grant, action="policy_revoked", actor="memory policy")

    def _match_summaries(self, request: dict[str, Any], matched_ids: list[str]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for memory_id in matched_ids:
            row = self.database.connection.execute(
                "SELECT id, title, type, project, status, visibility, metadata_json FROM documents "
                "WHERE id=? AND deleted_at IS NULL",
                (memory_id,),
            ).fetchone()
            if row is None:
                continue
            metadata = self._metadata(row)
            allowed_projects = metadata.get("allowed_projects") or []
            eligible = (
                row["status"] == "active"
                and row["visibility"] == "protected"
                and (not allowed_projects or request["project"] in allowed_projects)
            )
            summaries.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "type": row["type"],
                    "project": row["project"],
                    "access_policy": metadata.get("access_policy", "user_approval"),
                    "max_permission": self._max_permission(metadata),
                    "eligible": eligible,
                }
            )
        return summaries

    def dashboard_state(self) -> dict[str, Any]:
        requests = [
            dict(row)
            for row in self.database.connection.execute(
                "SELECT * FROM access_requests ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        ]
        for item in requests:
            matched_ids = json.loads(item.pop("matched_ids_json"))
            item["matched_count"] = len(matched_ids)
            item["matches"] = self._match_summaries(item, matched_ids)
            item.pop("query", None)
        grants = [
            dict(row)
            for row in self.database.connection.execute(
                "SELECT * FROM access_grants ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        ]
        for item in grants:
            item["scope_count"] = len(json.loads(item.pop("scope_ids_json")))
        events = [
            dict(row)
            for row in self.database.connection.execute(
                "SELECT * FROM access_events ORDER BY id DESC LIMIT 100"
            ).fetchall()
        ]
        return {"requests": requests, "grants": grants, "events": events}

    def record_sealed_unlock(self, *, memory_id: str, purpose: str) -> None:
        """Record a content-free, owner-only one-view unlock event."""
        self._event(
            agent="owner dashboard",
            action="sealed_unlocked",
            purpose=purpose,
            permission="read",
            scope=f"sealed memory {memory_id}",
            actor="owner",
            status="completed",
        )
