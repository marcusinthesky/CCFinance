"""Data layers and their processing commands."""

import typer

from pipeline.stages import processed, raw, research

app = typer.Typer(no_args_is_help=True, help="Data processing layers.")
app.add_typer(raw.app, name="raw", help=raw.__doc__)
app.add_typer(processed.app, name="processed", help=processed.__doc__)
app.add_typer(research.app, name="research", help=research.__doc__)


@app.command(name="list")
def list_stages() -> None:
    """List pipeline layers and their purpose."""
    for group in app.registered_groups:
        typer.echo(f"{group.name}: {group.help}")
