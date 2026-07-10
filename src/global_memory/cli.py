"""Administrative and MCP-routed command line interface."""

from __future__ import annotations

import typer

from global_memory import __version__

app = typer.Typer(
    name="global-memory",
    help="Manage a local, project-aware memory Vault through MCP.",
    no_args_is_help=True,
)


def version_callback(value: bool) -> None:
    """Print the package version and exit."""
    if value:
        typer.echo(f"global-memory {__version__}")
        raise typer.Exit


@app.callback()
def cli(
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show the installed package version.",
    ),
) -> None:
    """Run Global Memory administrative and runtime commands."""
    del version


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
