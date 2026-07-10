"""Administrative and MCP-routed command line interface."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, Never

import typer
from rich import print_json

from global_memory import __version__
from global_memory.config import get_platform_paths, load_settings
from global_memory.errors import GlobalMemoryError
from global_memory.mcp.client import call_http_tool
from global_memory.mcp.daemon_control import daemon_status, start_daemon, stop_daemon
from global_memory.vault.initialize import initialize

app = typer.Typer(
    name="global-memory",
    help="Manage a local, project-aware memory Vault through MCP.",
    no_args_is_help=True,
)
config_app = typer.Typer(name="config", help="Inspect and validate service configuration.")
daemon_app = typer.Typer(name="daemon", help="Manage the shared local MCP daemon.")
app.add_typer(config_app)
app.add_typer(daemon_app)


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
    """Run Global Memory administrative and runtime commands."""
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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
