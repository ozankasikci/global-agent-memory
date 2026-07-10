"""Administrative and MCP-routed command line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Never

import typer
from rich import print_json

from global_memory import __version__
from global_memory.config import get_platform_paths, load_settings
from global_memory.errors import GlobalMemoryError
from global_memory.vault.initialize import initialize

app = typer.Typer(
    name="global-memory",
    help="Manage a local, project-aware memory Vault through MCP.",
    no_args_is_help=True,
)
config_app = typer.Typer(name="config", help="Inspect and validate service configuration.")
app.add_typer(config_app)


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


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
