"""Administrative and MCP-routed command line interface."""

from __future__ import annotations

import asyncio
import json
import uuid
from argparse import Namespace
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Never

import typer
from rich import print_json

from global_memory import __version__
from global_memory.application.diagnostics_service import run_diagnostics
from global_memory.config import get_platform_paths, load_settings
from global_memory.errors import ErrorCode, GlobalMemoryError
from global_memory.integrations.manager import ClientName, IntegrationManager
from global_memory.integrations.verify import verify_client
from global_memory.mcp.client import call_http_tool
from global_memory.mcp.contract import load_discovery
from global_memory.mcp.daemon import run_daemon
from global_memory.mcp.daemon_control import daemon_status, start_daemon, stop_daemon
from global_memory.mcp.stdio_proxy import run_proxy
from global_memory.operations import (
    backup_vault,
    disable_service,
    enable_service,
    install_service,
    package_change,
    render_service_file,
    restore_vault,
    uninstall_service,
)
from global_memory.vault.initialize import initialize

app = typer.Typer(
    name="global-memory",
    help="Manage a local, project-aware memory Vault through MCP.",
    no_args_is_help=True,
)
config_app = typer.Typer(name="config", help="Inspect and validate service configuration.")
daemon_app = typer.Typer(name="daemon", help="Manage the shared local MCP daemon.")
project_app = typer.Typer(name="project", help="Manage project registry entries through MCP.")
mcp_app = typer.Typer(name="mcp", help="Run or inspect MCP transports and discovery.")
integrations_app = typer.Typer(name="integrations", help="Inspect and manage coding-client integration state.")
app.add_typer(config_app)
app.add_typer(daemon_app)
app.add_typer(project_app)
app.add_typer(mcp_app)
app.add_typer(integrations_app)


def version_callback(value: bool) -> None:
    """Print the package version and exit."""
    if value:
        typer.echo(f"global-memory {__version__}")
        raise typer.Exit


@app.callback()
def cli(
    version: Annotated[
        bool,
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show the installed package version."),
    ] = False,
) -> None:
    """Run Global Agent Memory administrative and runtime commands."""
    del version


def _fail(error: GlobalMemoryError) -> Never:
    typer.echo(f"{error.code.value}: {error.message}", err=True)
    if error.remediation:
        typer.echo(error.remediation, err=True)
    raise typer.Exit(code=2)


def _runtime_target(endpoint: str | None, token_file: Path | None, config_file: Path | None) -> tuple[str, Path]:
    paths = get_platform_paths()
    if endpoint is None:
        settings = load_settings(config_file or paths.config_file)
        endpoint = f"http://{settings.mcp.host}:{settings.mcp.port}/mcp/"
    return endpoint, token_file or paths.auth_token


def _call_runtime(
    name: str,
    arguments: dict[str, Any],
    *,
    endpoint: str | None,
    token_file: Path | None,
    config_file: Path | None,
) -> None:
    try:
        resolved_endpoint, resolved_token = _runtime_target(endpoint, token_file, config_file)
        envelope = asyncio.run(call_http_tool(resolved_endpoint, resolved_token, name, arguments))
    except GlobalMemoryError as error:
        _fail(error)
    print_json(data=envelope)
    if not envelope.get("ok"):
        raise typer.Exit(code=2)


@app.command("init")
def init_command(
    vault: Annotated[Path, typer.Option("--vault", resolve_path=True, help="Absolute path for the Obsidian Vault.")],
    config_file: Annotated[Path | None, typer.Option("--config", help="Optional existing TOML configuration.")] = None,
) -> None:
    """Initialize the Vault, local configuration, and protected token."""
    paths = get_platform_paths()
    try:
        settings = load_settings(config_file, {"vault_path": str(vault)})
        result = initialize(settings, paths)
    except GlobalMemoryError as error:
        _fail(error)
    state = "initialized" if result.created else "already initialized"
    typer.echo(f"Vault {state}: {result.vault_path}")
    typer.echo(f"Configuration: {result.config_file}")


@config_app.command("show")
def config_show(
    config_file: Annotated[
        Path | None, typer.Option("--config", help="TOML file; defaults to the platform path.")
    ] = None,
) -> None:
    """Display effective non-secret configuration as JSON."""
    path = config_file or get_platform_paths().config_file
    try:
        settings = load_settings(path)
    except GlobalMemoryError as error:
        _fail(error)
    print_json(data=settings.model_dump(mode="json"))


@config_app.command("validate")
def config_validate(
    config_file: Annotated[
        Path | None, typer.Option("--config", help="TOML file; defaults to the platform path.")
    ] = None,
) -> None:
    """Validate all configuration fields and explain any failures."""
    path = config_file or get_platform_paths().config_file
    try:
        load_settings(path)
    except GlobalMemoryError as error:
        _fail(error)
    typer.echo(f"Configuration is valid: {path}")


@app.command("doctor")
def doctor_command(
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")] = False,
) -> None:
    """Diagnose configuration, durable data, generated state, transports, and integrations."""
    paths = get_platform_paths()
    try:
        settings = load_settings(config_file or paths.config_file)
        report = asyncio.run(run_diagnostics(settings, paths))
    except GlobalMemoryError as error:
        _fail(error)
    if json_output:
        print_json(data=report.as_dict())
    else:
        for check in report.checks:
            typer.echo(f"[{check.status.upper()}] {check.name}: {check.message}")
    if not report.ok:
        raise typer.Exit(code=2)


@app.command("backup")
def backup_command(
    destination: Annotated[Path, typer.Argument()],
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Archive the canonical Markdown Vault without generated state or secrets."""
    paths = get_platform_paths()
    try:
        settings = load_settings(config_file or paths.config_file)
        result = backup_vault(settings.vault_path, destination)
    except GlobalMemoryError as error:
        _fail(error)
    typer.echo(f"Vault backup created: {result}")


@app.command("restore")
def restore_command(
    archive: Annotated[Path, typer.Argument()],
    vault: Annotated[Path, typer.Option("--vault")],
) -> None:
    """Restore a backup into an empty Vault destination."""
    try:
        count = restore_vault(archive, vault)
    except (GlobalMemoryError, OSError) as error:
        if isinstance(error, GlobalMemoryError):
            _fail(error)
        raise
    typer.echo(f"Restored {count} files to {vault}")


@app.command("upgrade")
def upgrade_command() -> None:
    """Upgrade the package in its active Python environment."""
    package_change()


@app.command("rollback")
def rollback_command(version: Annotated[str, typer.Argument()]) -> None:
    """Install one explicit prior package version."""
    package_change(version)


@app.command("status")
def status_command(
    endpoint: Annotated[str | None, typer.Option("--endpoint", help="Streamable HTTP MCP endpoint.")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file", help="Protected daemon token file.")] = None,
    config_file: Annotated[Path | None, typer.Option("--config", help="Configuration used for defaults.")] = None,
) -> None:
    """Read service status through MCP, never by opening SQLite directly."""
    _call_runtime("memory_status", {}, endpoint=endpoint, token_file=token_file, config_file=config_file)


@app.command("search")
def search_command(
    query: Annotated[str, typer.Argument(help="Text to search for.")],
    mode: Annotated[str, typer.Option("--mode", help="keyword, hybrid, semantic, or metadata.")] = "hybrid",
    project: Annotated[str | None, typer.Option("--project", help="Explicit project scope.")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint", help="Streamable HTTP MCP endpoint.")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file", help="Protected daemon token file.")] = None,
    config_file: Annotated[Path | None, typer.Option("--config", help="Configuration used for defaults.")] = None,
) -> None:
    """Search memory through the shared MCP daemon."""
    arguments: dict[str, Any] = {"query": query, "mode": mode}
    if project is not None:
        arguments["project"] = project
    _call_runtime(
        "memory_search",
        arguments,
        endpoint=endpoint,
        token_file=token_file,
        config_file=config_file,
    )


@app.command("context")
def context_command(
    task: Annotated[str, typer.Argument(help="Task that needs bounded memory context.")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    working_directory: Annotated[Path | None, typer.Option("--working-directory")] = None,
    token_budget: Annotated[int, typer.Option("--token-budget")] = 4000,
    cross_project: Annotated[bool, typer.Option("--cross-project")] = False,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Build bounded, diverse task context through MCP."""
    arguments: dict[str, Any] = {"task": task, "token_budget": token_budget, "cross_project": cross_project}
    if project:
        arguments["project"] = project
    if working_directory:
        arguments["working_directory"] = str(working_directory)
    _call_runtime("memory_context", arguments, endpoint=endpoint, token_file=token_file, config_file=config_file)


@app.command("remember")
def remember_command(
    title: Annotated[str, typer.Argument()],
    content: Annotated[str, typer.Argument()],
    memory_type: Annotated[str, typer.Option("--type")],
    scope: Annotated[str, typer.Option("--scope")],
    project: Annotated[str | None, typer.Option("--project")] = None,
    working_directory: Annotated[Path | None, typer.Option("--working-directory")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Create a review candidate through MCP."""
    arguments: dict[str, Any] = {
        "request_id": request_id or str(uuid.uuid4()),
        "title": title,
        "content": content,
        "type": memory_type,
        "scope": scope,
        "tags": tags or [],
        "force": force,
    }
    if project:
        arguments["project"] = project
    if working_directory:
        arguments["working_directory"] = str(working_directory)
    _call_runtime("memory_remember", arguments, endpoint=endpoint, token_file=token_file, config_file=config_file)


@app.command("get")
def get_command(
    memory_id: Annotated[str, typer.Argument()],
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Read one immutable memory ID through MCP."""
    _call_runtime("memory_get", {"id": memory_id}, endpoint=endpoint, token_file=token_file, config_file=config_file)


@app.command("approve")
def approve_command(
    memory_id: Annotated[str, typer.Argument()],
    expected_updated_at: Annotated[str | None, typer.Option("--expected-updated-at")] = None,
    destination_override: Annotated[str | None, typer.Option("--destination")] = None,
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Approve a candidate with optimistic concurrency."""
    arguments = {"request_id": request_id or str(uuid.uuid4()), "id": memory_id}
    if expected_updated_at:
        arguments["expected_updated_at"] = expected_updated_at
    if destination_override:
        arguments["destination_override"] = destination_override
    _call_runtime("memory_approve", arguments, endpoint=endpoint, token_file=token_file, config_file=config_file)


@app.command("reject")
def reject_command(
    memory_id: Annotated[str, typer.Argument()],
    reason: Annotated[str, typer.Option("--reason")],
    expected_updated_at: Annotated[str | None, typer.Option("--expected-updated-at")] = None,
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Reject a candidate with a durable reason."""
    arguments = {"request_id": request_id or str(uuid.uuid4()), "id": memory_id, "reason": reason}
    if expected_updated_at:
        arguments["expected_updated_at"] = expected_updated_at
    _call_runtime("memory_reject", arguments, endpoint=endpoint, token_file=token_file, config_file=config_file)


@app.command("update")
def update_command(
    memory_id: Annotated[str, typer.Argument()],
    expected_updated_at: Annotated[str, typer.Option("--expected-updated-at")],
    body: Annotated[str | None, typer.Option("--body")] = None,
    metadata_json: Annotated[str | None, typer.Option("--metadata-json")] = None,
    section_json: Annotated[str | None, typer.Option("--section-json")] = None,
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Update a read version through MCP using explicit patches."""
    arguments: dict[str, Any] = {
        "request_id": request_id or str(uuid.uuid4()),
        "id": memory_id,
        "expected_updated_at": expected_updated_at,
    }
    if body is not None:
        arguments["body"] = body
    if metadata_json:
        arguments["metadata_patch"] = json.loads(metadata_json)
    if section_json:
        arguments["section_patch"] = json.loads(section_json)
    _call_runtime("memory_update", arguments, endpoint=endpoint, token_file=token_file, config_file=config_file)


@app.command("supersede")
def supersede_command(
    old_id: Annotated[str, typer.Argument()],
    replacement_id: Annotated[str, typer.Argument()],
    reason: Annotated[str, typer.Option("--reason")],
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Supersede an active memory with an existing candidate or active memory."""
    _call_runtime(
        "memory_supersede",
        {
            "request_id": request_id or str(uuid.uuid4()),
            "old_id": old_id,
            "replacement_id": replacement_id,
            "reason": reason,
        },
        endpoint=endpoint,
        token_file=token_file,
        config_file=config_file,
    )


@app.command("archive")
def archive_command(
    memory_id: Annotated[str, typer.Argument()],
    reason: Annotated[str, typer.Option("--reason")],
    hard_delete: Annotated[bool, typer.Option("--hard-delete")] = False,
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Archive or explicitly hard-delete a memory through MCP."""
    _call_runtime(
        "memory_archive",
        {
            "request_id": request_id or str(uuid.uuid4()),
            "id": memory_id,
            "reason": reason,
            "hard_delete": hard_delete,
        },
        endpoint=endpoint,
        token_file=token_file,
        config_file=config_file,
    )


@app.command("reindex")
def reindex_command(
    full: Annotated[bool, typer.Option("--full")] = False,
    paths: Annotated[list[str] | None, typer.Option("--path")] = None,
    request_id: Annotated[str | None, typer.Option("--request-id")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Request a bounded or full generated-index rebuild through MCP."""
    _call_runtime(
        "memory_reindex",
        {"request_id": request_id or str(uuid.uuid4()), "full": full, "paths": paths or []},
        endpoint=endpoint,
        token_file=token_file,
        config_file=config_file,
    )


@daemon_app.command("start")
def daemon_start_command(
    config_file: Annotated[Path | None, typer.Option("--config", help="Configuration file.")] = None,
) -> None:
    """Start one managed daemon and wait for readiness."""
    paths = get_platform_paths()
    try:
        settings = load_settings(config_file or paths.config_file)
        state = start_daemon(settings, paths)
    except GlobalMemoryError as error:
        _fail(error)
    typer.echo(f"Daemon ready: {state.endpoint} (pid {state.pid})")


@daemon_app.command("status")
def daemon_status_command() -> None:
    """Verify the managed process identity and readiness endpoint."""
    state = daemon_status(get_platform_paths())
    if state is None:
        typer.echo("Daemon is stopped.")
        raise typer.Exit(code=1)
    typer.echo(f"Daemon is ready: {state.endpoint} (pid {state.pid})")


@daemon_app.command("stop")
def daemon_stop_command() -> None:
    """Stop the verified managed daemon without force-killing unrelated processes."""
    try:
        stopped = stop_daemon(get_platform_paths())
    except GlobalMemoryError as error:
        _fail(error)
    typer.echo("Daemon stopped." if stopped else "Daemon is already stopped.")


@daemon_app.command("install-service")
def daemon_install_service_command(
    kind: Annotated[str, typer.Option("--kind", help="launchd or systemd.")] = "launchd",
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
    enable: Annotated[bool, typer.Option("--enable/--no-enable")] = True,
) -> None:
    """Install and enable an idempotent per-user auto-start service."""
    paths = get_platform_paths()
    service = render_service_file(
        kind,
        config_file=config_file or paths.config_file,
        home=Path.home(),
    )
    try:
        installed = install_service(service)
        if enable:
            enable_service(service)
    except GlobalMemoryError as error:
        _fail(error)
    action = "Installed and enabled" if enable else "Installed"
    typer.echo(f"{action} {kind} service: {installed}")


@daemon_app.command("uninstall-service")
def daemon_uninstall_service_command(
    kind: Annotated[str, typer.Option("--kind", help="launchd or systemd.")] = "launchd",
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
    disable: Annotated[bool, typer.Option("--disable/--no-disable")] = True,
) -> None:
    """Remove only the marked service file managed by this product."""
    paths = get_platform_paths()
    service = render_service_file(
        kind,
        config_file=config_file or paths.config_file,
        home=Path.home(),
    )
    try:
        if disable and service.path.exists():
            disable_service(service)
        removed = uninstall_service(service)
    except GlobalMemoryError as error:
        _fail(error)
    typer.echo("Service removed." if removed else "Service is not installed.")


@app.command("serve")
def serve_command(
    config_file: Annotated[Path | None, typer.Option("--config", help="Configuration file.")] = None,
) -> None:
    """Run the authenticated daemon in the foreground."""
    paths = get_platform_paths()
    try:
        settings = load_settings(config_file or paths.config_file)
        arguments = Namespace(
            vault=settings.vault_path,
            state=paths.data_dir,
            token_file=paths.auth_token,
            host=settings.mcp.host,
            port=settings.mcp.port,
            max_request_bytes=settings.mcp.max_request_bytes,
            max_connections=64,
            instance_id=None,
            no_watch=not settings.index.watch,
            debounce_ms=settings.index.debounce_ms,
            exclude=settings.index.excluded_globs,
            embedding_provider="ollama" if settings.embeddings.enabled else "none",
            embedding_base_url=settings.embeddings.base_url,
            embedding_model=settings.embeddings.model,
            embedding_dimension=settings.embeddings.dimensions,
            embedding_batch_size=settings.embeddings.batch_size,
        )
        asyncio.run(run_daemon(arguments))
    except GlobalMemoryError as error:
        _fail(error)


def _project_call(
    action: str,
    payload: dict[str, Any],
    *,
    mutate: bool,
    endpoint: str | None,
    token_file: Path | None,
    config_file: Path | None,
) -> None:
    arguments: dict[str, Any] = {"action": action, "payload": payload}
    if mutate:
        arguments["request_id"] = str(uuid.uuid4())
    _call_runtime("memory_projects", arguments, endpoint=endpoint, token_file=token_file, config_file=config_file)


@project_app.command("list")
def project_list_command(
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """List configured projects through MCP."""
    _project_call("list", {}, mutate=False, endpoint=endpoint, token_file=token_file, config_file=config_file)


@project_app.command("get")
def project_get_command(
    identifier: Annotated[str, typer.Argument()],
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Read one project by ID or canonical name."""
    _project_call(
        "get",
        {"name": identifier},
        mutate=False,
        endpoint=endpoint,
        token_file=token_file,
        config_file=config_file,
    )


@project_app.command("detect")
def project_detect_command(
    working_directory: Annotated[Path, typer.Argument()],
    project: Annotated[str | None, typer.Option("--project")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Run the canonical project detector through MCP."""
    payload = {"working_directory": str(working_directory)}
    if project:
        payload["project"] = project
    _project_call("detect", payload, mutate=False, endpoint=endpoint, token_file=token_file, config_file=config_file)


@project_app.command("add")
def project_add_command(
    name: Annotated[str, typer.Argument()],
    root: Annotated[list[str] | None, typer.Option("--root")] = None,
    remote: Annotated[list[str] | None, typer.Option("--remote")] = None,
    alias: Annotated[list[str] | None, typer.Option("--alias")] = None,
    organization: Annotated[str | None, typer.Option("--organization")] = None,
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Add a project registry entry through MCP."""
    payload: dict[str, Any] = {
        "name": name,
        "roots": root or [],
        "git_remotes": remote or [],
        "aliases": alias or [],
    }
    if organization:
        payload["organization"] = organization
    _project_call("add", payload, mutate=True, endpoint=endpoint, token_file=token_file, config_file=config_file)


@project_app.command("update")
def project_update_command(
    identifier: Annotated[str, typer.Argument()],
    patch_json: Annotated[str, typer.Option("--patch-json")],
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Patch a project through MCP."""
    _project_call(
        "update",
        {"name": identifier, "patch": json.loads(patch_json)},
        mutate=True,
        endpoint=endpoint,
        token_file=token_file,
        config_file=config_file,
    )


@project_app.command("deactivate")
def project_deactivate_command(
    identifier: Annotated[str, typer.Argument()],
    endpoint: Annotated[str | None, typer.Option("--endpoint")] = None,
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Deactivate a project through MCP."""
    _project_call(
        "deactivate",
        {"name": identifier},
        mutate=True,
        endpoint=endpoint,
        token_file=token_file,
        config_file=config_file,
    )


@mcp_app.command("discovery")
def mcp_discovery_command() -> None:
    """Print the frozen generated MCP V1 discovery document."""
    print_json(data=load_discovery())


@mcp_app.command("proxy")
def mcp_proxy_command(
    endpoint: Annotated[str, typer.Option("--endpoint")] = "http://127.0.0.1:8765/mcp/",
    token_file: Annotated[Path | None, typer.Option("--token-file")] = None,
) -> None:
    """Run the protocol-pure stdio proxy in the foreground."""
    asyncio.run(run_proxy(endpoint, token_file or get_platform_paths().auth_token))


def _integration_targets(target: str) -> list[ClientName]:
    if target == "all":
        return ["claude-code", "codex"]
    if target not in {"claude-code", "codex"}:
        raise GlobalMemoryError(ErrorCode.CONFIG_INVALID, "Target must be claude-code, codex, or all.")
    return [target]  # type: ignore[list-item]


def _integration_manager(config_file: Path | None = None) -> IntegrationManager:
    paths = get_platform_paths()
    settings = load_settings(config_file or paths.config_file)
    return IntegrationManager(
        Path.home(),
        paths.data_dir,
        endpoint=f"http://{settings.mcp.host}:{settings.mcp.port}/mcp/",
        token_file=paths.auth_token,
    )


@integrations_app.command("install")
def integrations_install_command(
    target: Annotated[str, typer.Argument(help="claude-code, codex, or all")],
    copy: Annotated[bool, typer.Option("--copy", help="Copy instead of symlinking the skill.")] = False,
    with_global_instructions: Annotated[bool, typer.Option("--with-global-instructions")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    force: Annotated[bool, typer.Option("--force")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Install the canonical skill and user-scoped stdio MCP registration safely."""
    try:
        manager = _integration_manager(config_file)
        results = [
            asdict(
                manager.install(
                    client,
                    copy=copy,
                    with_global_instructions=with_global_instructions,
                    dry_run=dry_run,
                    force=force,
                )
            )
            for client in _integration_targets(target)
        ]
    except GlobalMemoryError as error:
        _fail(error)
    if json_output:
        print_json(data=results)
    else:
        for result in results:
            typer.echo(f"{result['name']}: {result['skill_path']} ({result['skill_mode']})")


@integrations_app.command("status")
def integrations_status_command(
    target: Annotated[str, typer.Argument(help="claude-code, codex, or all")] = "all",
    json_output: Annotated[bool, typer.Option("--json")] = False,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Show managed skill and MCP registration integrity."""
    try:
        manager = _integration_manager(config_file)
        results = [manager.status(client) for client in _integration_targets(target)]
    except GlobalMemoryError as error:
        _fail(error)
    if json_output:
        print_json(data=results)
    else:
        for result in results:
            typer.echo(
                f"{result['client']}: skill={'ok' if result['skill_valid'] else 'missing/changed'}, "
                f"mcp={'registered' if result['mcp_registered'] else 'missing'}"
            )


@integrations_app.command("verify")
def integrations_verify_command(
    target: Annotated[str, typer.Argument(help="claude-code, codex, or all")],
    json_output: Annotated[bool, typer.Option("--json")] = False,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Run installation, MCP discovery, lifecycle, Git detection, and isolation acceptance."""
    try:
        manager = _integration_manager(config_file)
        reports = [asyncio.run(verify_client(manager, client)) for client in _integration_targets(target)]
    except GlobalMemoryError as error:
        _fail(error)
    values = [report.as_dict() for report in reports]
    if json_output:
        print_json(data=values)
    else:
        for report in reports:
            typer.echo(f"{report.client}: {'verified' if report.ok else 'failed'}")
    if not all(report.ok for report in reports):
        raise typer.Exit(code=2)


@integrations_app.command("uninstall")
def integrations_uninstall_command(
    target: Annotated[str, typer.Argument(help="claude-code, codex, or all")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
    config_file: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Remove only artifacts recorded in the integration manifest."""
    try:
        manager = _integration_manager(config_file)
        results = {client: manager.uninstall(client, dry_run=dry_run) for client in _integration_targets(target)}
    except GlobalMemoryError as error:
        _fail(error)
    if json_output:
        print_json(data=results)
    else:
        for client, removed in results.items():
            typer.echo(f"{client}: {'removed' if removed else 'not installed'}")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
